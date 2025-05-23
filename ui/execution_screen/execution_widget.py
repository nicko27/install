"""
Widget principal d'exécution de plugins.

Ce module fournit le widget central responsable de l'affichage et de l'exécution
des plugins configurés, avec gestion des logs et de la progression.
"""

from typing import Dict, List, Any, Optional, Tuple, Set
import traceback
import sys
import os
import json
import re
import asyncio

from textual.app import ComposeResult, App
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Checkbox, Label, ProgressBar, Static, Footer, Header
from textual.reactive import reactive
from textual.binding import Binding

from .plugin_container import PluginContainer
from .local_executor import LocalExecutor
from .ssh_executor import SSHExecutor
from .logger_utils import LoggerUtils
from ..utils.messaging import Message, MessageType
from ..choice_screen.plugin_utils import get_plugin_folder_name
from ..utils.logging import get_logger
from ..ssh_manager.ip_utils import get_target_ips

logger = get_logger('execution_widget')

class ExecutionWidget(Container):
    """
    Widget principal d'exécution des plugins.

    Ce widget coordonne l'affichage et l'exécution de tous les plugins configurés,
    y compris leur exécution locale ou distante via SSH.
    """

    # États réactifs
    is_running = reactive(False)  # État d'exécution
    continue_on_error = reactive(True)  # Continuer même en cas d'erreur (True par défaut)
    show_logs = reactive(True)  # Logs visibles par défaut
    back_button_clicked = reactive(False)  # Suivi du bouton retour

    def __init__(self, plugins_config: Optional[Dict[str, Any]] = None):
        """
        Initialise le widget avec la configuration des plugins.

        Args:
            plugins_config: Dictionnaire de configuration des plugins
        """
        super().__init__()
        self.plugins: Dict[str, PluginContainer] = {}
        self.plugins_config = plugins_config or {}
        self._current_plugin = None
        self._total_plugins = 0
        self._executed_plugins = 0
        self.sequence_name = None
        self._app_ref = None  # Référence à l'application, définie lors du montage

        # Extraire le nom de la séquence si présent
        self._extract_sequence_name()

        logger.debug(f"ExecutionWidget initialisé avec {len(self.plugins_config)} plugins")
        logger.debug(f"Plugins disponibles: {list(self.plugins_config.keys())}")

    def _extract_sequence_name(self) -> None:
        """Extrait le nom de la séquence depuis la configuration des plugins."""
        for plugin_id, config in self.plugins_config.items():
            plugin_name = config.get('plugin_name', '')
            if isinstance(plugin_name, str) and plugin_name.startswith('__sequence__'):
                sequence_file = plugin_name.replace('__sequence__', '')
                self.sequence_name = sequence_file.replace('.yml', '')
                logger.debug(f"Séquence détectée: {self.sequence_name}")
                break

    async def execute_plugin(self, plugin_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Exécute un plugin spécifique localement ou via SSH.

        Args:
            plugin_id: Identifiant du plugin à exécuter
            config: Configuration du plugin

        Returns:
            Dict[str, Any]: Résultat de l'exécution {success, output}
        """
        try:
            # Vérifier si la configuration est valide
            if not isinstance(config, dict):
                logger.error(f"Configuration invalide pour {plugin_id}: {config}")
                return {
                    'success': False,
                    'output': f"Erreur: Configuration invalide pour le plugin {plugin_id}"
                }

            # Extraire les informations de base
            plugin_name = self._get_plugin_name(plugin_id, config)
            plugin_config = self._extract_plugin_config(config)
            instance_id = config.get('instance_id', plugin_id)
            show_name = config.get('show_name', config.get('name', plugin_name))
            icon = config.get('icon', '📦')

            # Ignorer les séquences
            if isinstance(plugin_name, str) and plugin_name.startswith('__sequence__'):
                logger.warning(f"Tentative d'exécution d'une séquence: {plugin_name}")
                return False

            # Récupérer le dossier du plugin
            folder_name = get_plugin_folder_name(plugin_name)
            logger.debug(f"Dossier du plugin {plugin_name} (ID: {instance_id}): {folder_name}")
            logger.debug(f"Configuration: {plugin_config}")

            # Déterminer le mode d'exécution (local ou SSH)
            remote_execution = config.get('remote_execution', False)
            executor = self._create_executor(plugin_id, folder_name, plugin_config, remote_execution)

            # Exécuter le plugin
            plugin_widget = self.plugins.get(plugin_id)
            status = await executor.execute_plugin(plugin_widget, folder_name, config)
            return status


        except Exception as e:
            logger.error(f"Erreur lors de l'exécution du plugin {plugin_id}: {e}")
            logger.error(traceback.format_exc())

            # Ajouter des informations sur l'IP cible en cas d'erreur SSH
            plugin_widget = self.plugins.get(plugin_id)
            target_ip = getattr(plugin_widget, 'target_ip', None) if plugin_widget else None

            # Log avec IP si disponible
            error_msg = str(e)
            if target_ip:
                logger.error(f"Erreur sur {target_ip}: {error_msg}")
                output_msg = f"Erreur d'exécution sur {target_ip}: {error_msg}"
            else:
                output_msg = f"Erreur d'exécution: {error_msg}"

            return False

    def _get_plugin_name(self, plugin_id: str, config: Dict[str, Any]) -> str:
        """
        Détermine le nom du plugin à partir de sa configuration.

        Args:
            plugin_id: Identifiant du plugin
            config: Configuration du plugin

        Returns:
            str: Nom du plugin
        """
        plugin_name = config.get('plugin_name', '')
        if not plugin_name:
            # Si pas de nom, utiliser le dossier comme nom
            plugin_name = get_plugin_folder_name(str(plugin_id))
            logger.debug(f"Utilisation du dossier comme nom: {plugin_name}")
        return plugin_name

    def _extract_plugin_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extrait la configuration effective du plugin.

        Args:
            config: Configuration complète

        Returns:
            Dict[str, Any]: Configuration nettoyée
        """
        # Si une clé 'config' existe, l'utiliser
        if 'config' in config:
            return config['config']

        # Sinon, copier toutes les clés sauf celles spéciales
        special_keys = {'plugin_name', 'instance_id', 'show_name', 'icon', 'remote_execution'}
        return {k: v for k, v in config.items() if k not in special_keys}

    def _create_executor(self, plugin_id: str, folder_name: str,
                        plugin_config: Dict[str, Any], remote_execution: bool) -> Any:
        """
        Crée l'exécuteur approprié (local ou SSH) pour le plugin.

        Args:
            plugin_id: Identifiant du plugin
            folder_name: Nom du dossier du plugin
            plugin_config: Configuration du plugin
            remote_execution: Si True, utilise l'exécution SSH

        Returns:
            Any: Exécuteur configuré
        """
        if remote_execution:
            logger.debug(f"Création d'un exécuteur SSH pour {plugin_id}")
            # Configuration pour l'exécuteur SSH
            ssh_config = {
                'plugin_name': folder_name,
                'instance_id': plugin_id.split('_')[-1] if '_' in plugin_id else plugin_id,
                'config': plugin_config,
                'ssh_debug': plugin_config.get('ssh_debug', False)
            }
            return SSHExecutor(ssh_config)
        else:
            logger.debug(f"Création d'un exécuteur local pour {plugin_id}")
            return LocalExecutor(self.app if self._app_ref is None else self._app_ref)

    async def run_plugins(self) -> None:
        """
        Exécute tous les plugins de façon séquentielle.

        Cette méthode est le cœur du processus d'exécution, gérant l'ordre,
        les erreurs et la mise à jour de l'interface.
        """
        try:
            await LoggerUtils.start_logs_timer(self)
            # Préparer l'exécution
            filtered_plugins, filtered_configs, ordered_plugins = self._prepare_plugins_execution()

            # Vérification de la préparation
            if not ordered_plugins:
                await LoggerUtils.add_log(self, "Aucun plugin à exécuter", level="warning")
                return

            total_plugins = len(ordered_plugins)
            executed = 0

            # Initialiser l'interface
            self._initialize_execution_ui()
            await LoggerUtils.add_log(self, f"Démarrage de l'exécution de {total_plugins} plugins", level="info")

            # Exécuter chaque plugin dans l'ordre
            for plugin_id in ordered_plugins:
                if not self.is_running:
                    logger.info("Exécution arrêtée par l'utilisateur")
                    break

                # Récupérer le plugin et sa configuration
                plugin_widget = filtered_plugins[plugin_id]
                config = filtered_configs[plugin_id]
                plugin_name = plugin_widget.plugin_name

                # Mettre à jour l'interface
                self.set_current_plugin(plugin_name)
                self.update_global_progress(executed / total_plugins * 100)

                try:
                    # Initialiser la progression
                    plugin_widget.update_progress(0.0, "En cours")

                    # Exécuter le plugin
                    logger.debug(f"Exécution du plugin {plugin_id}")
                    result = await self.execute_plugin(plugin_id, config)


                    # Mise à jour du statut et de la sortie
                    self._update_plugin_status(plugin_widget, result)



                except Exception as e:
                    logger.error(f"Erreur lors de l'exécution de {plugin_id}: {e}")
                    logger.error(traceback.format_exc())

                    # Mise à jour du statut du plugin en cas d'erreur
                    plugin_widget.set_status("error")
                    plugin_widget.set_output(f"Erreur")
                    plugin_widget.update_progress(100.0, "Erreur")

                    # Si on ne continue pas en cas d'erreur, arrêter l'exécution
                    if not self.continue_on_error:
                        logger.warning(f"Arrêt de l'exécution après erreur sur {plugin_id}")
                        break

                executed += 1
                self.update_global_progress(executed / total_plugins * 100)

            # Afficher un message de fin d'exécution
            self._display_execution_summary(executed, total_plugins)

        except Exception as e:
            logger.error(f"Erreur globale lors de l'exécution: {e}")
            logger.error(traceback.format_exc())
            await LoggerUtils.add_log(self, f"Erreur lors de l'exécution: {e}", level="error")
        finally:
            # Arrêter le timer d'affichage des logs
            await LoggerUtils.stop_logs_timer()

            # Afficher un dernier lot de messages en attente
            await LoggerUtils.flush_pending_messages(self)

    def _prepare_plugins_execution(self) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
        """
        Prépare les plugins pour l'exécution en filtrant les séquences.

        Returns:
            Tuple: (plugins_filtrés, configs_filtrées, ordre_exécution)
        """
        # Identifier les plugins de séquence
        filtered_plugins = {}
        filtered_configs = {}
        sequence_plugin_ids = []

        # Identifier les plugins de séquence principaux
        for plugin_id, config in self.plugins_config.items():
            plugin_name = config.get('plugin_name', '')
            if isinstance(plugin_name, str) and plugin_name.startswith('__sequence__'):
                sequence_plugin_ids.append(plugin_id)
                logger.debug(f"Séquence principale identifiée: {plugin_id}")

        # Créer une liste ordonnée pour l'exécution
        ordered_plugins = []

        # Filtrer les plugins et créer l'ordre d'exécution
        for plugin_id, plugin in self.plugins.items():
            # Ignorer les séquences principales
            if plugin_id in sequence_plugin_ids:
                continue

            # Vérifier si la configuration existe
            if plugin_id in self.plugins_config:
                filtered_plugins[plugin_id] = plugin
                filtered_configs[plugin_id] = self.plugins_config[plugin_id]
                ordered_plugins.append(plugin_id)
                logger.debug(f"Plugin ajouté: {plugin_id}")
            else:
                logger.warning(f"Configuration manquante pour {plugin_id}")

        logger.debug(f"Préparation terminée: {len(ordered_plugins)} plugins à exécuter")
        return filtered_plugins, filtered_configs, ordered_plugins

    def _initialize_execution_ui(self) -> None:
        """Initialise l'interface pour l'exécution."""
        # S'assurer que les logs sont visibles
        logs_container = self.query_one("#logs-container", ScrollableContainer)
        if logs_container and "hidden" in logs_container.classes:
            logs_container.remove_class("hidden")
            self.show_logs = True

    def _update_plugin_status(self, plugin_widget: PluginContainer,
                             status: bool) -> None:
        """
        Met à jour le statut et la sortie d'un plugin après exécution.

        Args:
            plugin_widget: Widget du plugin
            status: Résultat de l'exécution
        """
        try:
            # Mettre à jour le statut
            if status:
                plugin_widget.set_status("success")
                plugin_widget.set_output("OK")
            else:
                plugin_widget.set_status("error")
                plugin_widget.set_output("Erreur")
            # Mettre à jour la sortie

            # Mettre à jour la progression
            plugin_widget.update_progress(100.0, "Terminé" if status else "Échec")
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du statut: {e}")

    async def _display_execution_summary(self, executed: int, total: int) -> None:
        """
        Affiche un résumé de l'exécution dans les logs.

        Args:
            executed: Nombre de plugins exécutés
            total: Nombre total de plugins
        """
        # Vérifier s'il y a eu des erreurs
        has_errors = False
        for plugin_id, plugin_widget in self.plugins.items():
            if plugin_widget.status == "error":
                has_errors = True
                break

        # Déterminer le niveau de log
        if has_errors:
            level = "error"
        elif executed < total:
            level = "warning"
        else:
            level = "success"

        # Construire le message
        texte_plugin = "plugins exécutés" if executed > 1 else "plugin exécuté"
        message = f"Exécution terminée : {executed}/{total} {texte_plugin}"

        if has_errors:
            message += " (des erreurs ont été détectées)"
        elif executed < total:
            message += " (certains plugins n'ont pas été exécutés)"

        await LoggerUtils.add_log(self, message, level=level)

    async def start_execution(self, auto_mode: bool = False) -> None:
        """
        Démarre l'exécution des plugins.

        Args:
            auto_mode: Si True, l'exécution est lancée automatiquement
        """
        # Vérifier si une exécution est déjà en cours
        if self.is_running:
            logger.debug("Une exécution est déjà en cours")
            return

        # Récupérer les boutons
        start_button = self.query_one("#start-button")
        back_button = self.query_one("#back-button")
        if not start_button:
            logger.error("Bouton de démarrage introuvable")
            return

        try:
            # Démarrer l'exécution
            self.is_running = True
            logger.info("Démarrage de l'exécution")

            # Masquer les boutons pendant l'exécution
            start_button.add_class("hidden")
            back_button.add_class("hidden")
            logger.debug("Boutons masqués")

            # Réinitialiser l'interface
            self.update_global_progress(0)
            self.logs_text.update("")
            self.logs_text.auto_refresh=True
            await LoggerUtils.clear_logs(self)

            # Exécuter les plugins
            await self.run_plugins()

            # Notifier la fin de l'exécution
            logger.debug("Notification de fin d'exécution")
            if hasattr(self.app.screen, 'on_execution_completed'):
                await self.app.screen.on_execution_completed()

            # Réafficher les boutons après l'exécution si pas en mode auto
            if not auto_mode:
                start_button.remove_class("hidden")
                back_button.remove_class("hidden")
                logger.debug("Boutons réaffichés après exécution")

            try:
                await LoggerUtils.flush_pending_messages(self.app)
                # Force un second flush après une courte pause
                await asyncio.sleep(0.1)
                await LoggerUtils.flush_pending_messages(self.app)
                # Rafraîchir l'UI après le flush
                self.refresh()
            except Exception as e:
                logger.error(f"Erreur lors du flush final des logs: {e}")


        except Exception as e:
            logger.error(f"Erreur lors du démarrage de l'exécution: {e}")
            logger.error(traceback.format_exc())

            # Afficher un message d'erreur
            error_msg = Message(
                type=MessageType.ERROR,
                content=f"Erreur lors du démarrage: {e}"
            )
            await LoggerUtils.display_message(self, error_msg)

            # Réafficher les boutons en cas d'erreur
            start_button.remove_class("hidden")
            back_button.remove_class("hidden")

        finally:
            self.is_running = False
            self.back_button_clicked = False



    def update_global_progress(self, progress: float) -> None:
        """
        Met à jour la barre de progression globale.

        Args:
            progress: Valeur de progression (0-100)
        """
        try:
            # Essayer de trouver la barre de progression
            try:
                progress_bar = self.query_one("#global-progress")
                if progress_bar:
                    progress_bar.update(total=100.0, progress=progress)
                    logger.debug(f"Progression mise à jour: {progress}%")
            except Exception as e:
                logger.debug(f"Barre de progression non trouvée: {e}")

                # Essayer de la créer si elle n'existe pas
                button_container = self.query_one("#button-container")
                if button_container:
                    # Vérifier si elle existe déjà
                    existing_bars = [w for w in button_container.children
                                    if getattr(w, "id", "") == "global-progress"]
                    if existing_bars:
                        existing_bars[0].update(total=100.0, progress=progress)
                    else:
                        # Créer une nouvelle barre
                        from textual.widgets import ProgressBar
                        new_bar = ProgressBar(id="global-progress", show_eta=False)
                        new_bar.total = 100.0
                        new_bar.progress = progress
                        button_container.mount(new_bar)
                        logger.debug("Nouvelle barre de progression créée")
        except Exception as e:
            logger.error(f"Impossible de mettre à jour la progression: {e}")

    def set_current_plugin(self, plugin_name: str) -> None:
        """
        Met à jour l'affichage du plugin courant et scrolle vers lui.

        Args:
            plugin_name: Nom du plugin en cours d'exécution
        """
        try:
            # Scroller vers le plugin en cours
            if plugin_name != "aucun":
                try:
                    plugins_list = self.query_one("#plugins-list")
                    if plugins_list:
                        for plugin_id, plugin in self.plugins.items():
                            if plugin.plugin_name == plugin_name:
                                # Scroller vers le plugin
                                plugin.scroll_visible()
                                break
                except Exception as e:
                    logger.debug(f"Impossible de scroller vers {plugin_name}: {e}")
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du plugin courant: {e}")

    def action_toggle_logs(self) -> None:
        """Affiche ou masque les logs."""
        LoggerUtils.toggle_logs(self)

    async def display_log(self, message: str, level: str = "info") -> None:
        """
        Affiche un message dans les logs (compatibilité avec anciens systèmes).

        Args:
            message: Message à afficher
            level: Niveau du message (info, warning, error, success)
        """
        await LoggerUtils.add_log(self, message, level)

    def sanitize_id(self, id_string: str) -> str:
        """
        Assainit une chaîne pour l'utiliser comme ID en supprimant les caractères invalides.

        Args:
            id_string: Chaîne à assainir

        Returns:
            str: Chaîne assainie
        """
        return ''.join(c if c.isalnum() or c in '-_' else '_' for c in id_string)

    def _create_ssh_plugin_containers(self, plugin_id: str, config: Dict[str, Any],
                                    plugin_name: str, show_name: str, icon: str) -> List[str]:
        """
        Crée des conteneurs pour un plugin SSH avec plusieurs IPs.

        Args:
            plugin_id: ID du plugin
            config: Configuration du plugin
            plugin_name: Nom du plugin
            show_name: Nom à afficher
            icon: Icône du plugin

        Returns:
            List[str]: Liste des IDs de conteneurs créés
        """
        created_containers = []
        plugin_config = config.get('config', {})
        ssh_ips = plugin_config.get('ssh_ips', '')
        ssh_exception_ips = plugin_config.get('ssh_exception_ips', '')

        # Si le plugin a plusieurs IPs
        if ssh_ips and ('*' in ssh_ips or ',' in ssh_ips):
            # Obtenir la liste des IPs cibles
            target_ips = get_target_ips(ssh_ips, ssh_exception_ips)
            logger.debug(f"Plugin SSH {plugin_id} avec {len(target_ips)} IPs: {target_ips}")

            if target_ips:
                # Créer un conteneur pour chaque IP
                for ip in target_ips:
                    # Créer un ID unique
                    ip_plugin_id = f"{plugin_id}_{ip.replace('.', '_')}"

                    # Vérifier si ce conteneur existe déjà
                    if ip_plugin_id in self.plugins:
                        logger.debug(f"Conteneur déjà existant pour {ip_plugin_id}")
                        continue

                    # Assainir l'ID
                    sanitized_id = self.sanitize_id(ip_plugin_id)

                    # Créer le conteneur avec l'IP dans le nom
                    ip_show_name = f"{show_name} ({ip})"
                    container = PluginContainer(sanitized_id, plugin_name, ip_show_name, icon)

                    # Stocker l'IP cible
                    container.target_ip = ip

                    # Ajouter aux plugins
                    self.plugins[ip_plugin_id] = container

                    # Créer une copie de la configuration pour cette IP
                    ip_config = config.copy()
                    self.plugins_config[ip_plugin_id] = ip_config

                    logger.debug(f"Conteneur ajouté pour {ip_plugin_id}: {ip_show_name}")
                    created_containers.append(ip_plugin_id)

                    yield container
            else:
                # Aucune IP valide, créer un conteneur d'erreur
                if plugin_id not in self.plugins:
                    sanitized_id = self.sanitize_id(plugin_id)
                    container = PluginContainer(sanitized_id, plugin_name,
                                              f"{show_name} (Aucune IP valide)", icon)
                    self.plugins[plugin_id] = container
                    logger.debug(f"Conteneur d'erreur ajouté pour {plugin_id}")
                    created_containers.append(plugin_id)

                    yield container

        return created_containers

    def compose(self) -> ComposeResult:
        """
        Compose l'interface du widget d'exécution.

        Returns:
            ComposeResult: Résultat de la composition
        """
        # En-tête avec le nom de la séquence si disponible
        header_text = "Exécution des plugins"
        if self.sequence_name:
            header_text = f"Exécution de la séquence: {self.sequence_name}"
        yield Header(name=header_text)

        # Liste des plugins
        with ScrollableContainer(id="plugins-list"):
            logger.debug(f"Création des conteneurs pour {len(self.plugins_config)} plugins")
            processed_plugins = set()

            # Copie du dictionnaire pour éviter les erreurs de taille
            plugins_config_copy = self.plugins_config.copy()

            for plugin_id, config in plugins_config_copy.items():
                # Ignorer les séquences
                plugin_name = config.get('plugin_name', '')
                if isinstance(plugin_name, str) and plugin_name.startswith('__sequence__'):
                    logger.debug(f"Ignoré séquence: {plugin_name}")
                    continue

                # Vérifier si déjà traité
                if plugin_id in processed_plugins:
                    logger.debug(f"Plugin {plugin_id} déjà traité")
                    continue

                processed_plugins.add(plugin_id)

                # Récupérer les informations du plugin
                if not plugin_name:
                    plugin_name = get_plugin_folder_name(str(plugin_id))

                show_name = config.get('name', plugin_name)
                icon = config.get('icon', '📦')

                # Créer le conteneur avec ID unique
                plugin_container = PluginContainer(
                    plugin_id=plugin_id,
                    plugin_name=plugin_name,
                    plugin_show_name=show_name,
                    plugin_icon=icon
                )

                # Vérifier que le conteneur a été créé correctement
                if plugin_container.id:
                    self.plugins[plugin_id] = plugin_container
                    yield plugin_container
                else:
                    logger.error(f"Impossible de créer un conteneur pour {plugin_id}")

                # Créer des conteneurs supplémentaires pour SSH multi-IPs
                plugin_config = config.get('config', {})
                ssh_ips = plugin_config.get('ssh_ips', '')

                if ssh_ips and ('*' in ssh_ips or ',' in ssh_ips):
                    yield from self._create_ssh_plugin_containers(
                        plugin_id, config, plugin_name, show_name, icon
                    )
                elif ssh_ips:
                    # Plugin SSH avec une seule IP
                    if plugin_id not in self.plugins:
                        sanitized_id = self.sanitize_id(plugin_id)
                        container = PluginContainer(sanitized_id, plugin_name, show_name, icon)
                        container.target_ip = ssh_ips.strip()
                        self.plugins[plugin_id] = container
                        logger.debug(f"Conteneur SSH simple ajouté pour {plugin_id}")
                        yield container

        # Zone des logs
        with Horizontal(id="logs"):
            with ScrollableContainer(id="logs-container", classes=""):
                self.logs_text = Static("", id="logs-text")
                yield self.logs_text

        # Boutons et contrôles
        with Horizontal(id="button-container"):
            with Vertical(id="button-container-back-exec"):
                yield Button("Retour", id="back-button", variant="error")
            with Vertical(id="button-container-continue-exec"):
                yield Checkbox("Continuer en cas d'erreur", id="continue-on-error", value=True)
            # Initialiser la barre de progression avec des valeurs par défaut
            with Vertical(id="button-container-progress-exec"):
                progress_bar = ProgressBar(id="global-progress", show_eta=False)
                progress_bar.total = 100.0
                yield progress_bar
            # Bouton de démarrage
            with Vertical(id="button-container-start-exec"):
                yield Button("Démarrer", id="start-button", variant="primary")

        yield Footer()

    async def on_mount(self) -> None:
        """
        Appelé au montage initial du widget.
        Initialise l'interface et les références.
        """
        # Récupérer la référence à l'application
        self._app_ref = self.app
        logger.debug(f"ExecutionWidget monté, app={self._app_ref}")

        # Initialiser l'interface après rafraîchissement
        self.call_after_refresh(self.initialize_ui)

    async def initialize_ui(self) -> None:
        """Initialise l'interface après le montage complet du DOM."""
        try:
            # Initialisation de base
            self.update_global_progress(0)

            # S'assurer que les logs sont visibles
            logs_container = self.query_one("#logs-container", ScrollableContainer)
            if logs_container and "hidden" in logs_container.classes:
                logs_container.remove_class("hidden")
                self.show_logs = True

            # Gérer l'affichage du bouton démarrer
            start_button = self.query_one("#start-button")
            if start_button and self.back_button_clicked:
                start_button.remove_class("hidden")
                logger.debug("Bouton démarrer affiché")

            # Initialiser les options
            self.continue_on_error = True  # True par défaut

            # Vider les logs
            await LoggerUtils.clear_logs(self)

            # IMPORTANT: Afficher les messages en attente maintenant que l'interface est prête
            # Ajouter un délai court pour s'assurer que l'interface est complètement rendue
            await asyncio.sleep(0.1)
            await LoggerUtils.flush_pending_messages(self)

        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de l'interface: {e}")
            logger.error(traceback.format_exc())

    async def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """
        Gère le changement d'état des cases à cocher.

        Args:
            event: Événement de changement
        """
        if event.checkbox.id == "continue-on-error":
            self.continue_on_error = event.value
            logger.debug(f"Option 'continuer en cas d'erreur' changée: {self.continue_on_error}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Gère les clics sur les boutons.

        Args:
            event: Événement de bouton pressé
        """
        button_id = event.button.id
        logger.debug(f"Clic sur le bouton {button_id}")

        if not button_id:
            logger.warning("Bouton sans identifiant détecté")
            return

        try:
            if button_id == "start-button" and not event.button.disabled:
                # Démarrer l'exécution
                await self.start_execution()
            elif button_id == "back-button":
                # Marquer que le bouton retour a été cliqué
                self.back_button_clicked = True
                logger.debug("Retour à l'écran de configuration")

                await self._return_to_config_screen()
            elif button_id == "toggle-logs-button":
                # Afficher/masquer les logs
                self.action_toggle_logs()
        except Exception as e:
            logger.error(f"Erreur lors du traitement du clic sur {button_id}: {e}")
            logger.error(traceback.format_exc())
            # En cas d'erreur, réactiver le bouton
            if button_id == "start-button":
                event.button.disabled = False

    async def _return_to_config_screen(self) -> None:
        """
        Retourne à l'écran de configuration en préservant les configurations.
        """
        try:
            # Import ici pour éviter les imports circulaires
            from ..config_screen.config_screen import PluginConfig

            # Extraire les infos de plugin pour l'écran de configuration
            plugin_instances = []

            for plugin_id in self.plugins_config.keys():
                # Récupérer la configuration
                config = self.plugins_config.get(plugin_id, {})
                if not isinstance(config, dict):
                    continue

                # Ignorer les séquences
                plugin_name = config.get('plugin_name', '')
                if isinstance(plugin_name, str) and plugin_name.startswith('__sequence__'):
                    continue

                try:
                    # Récupérer le dossier du plugin
                    folder_name = get_plugin_folder_name(plugin_name)
                    # Utiliser l'instance ID de la configuration
                    instance_id = config.get('instance_id', 0)
                    # Ajouter le tuple (nom_plugin, instance_id)
                    plugin_instances.append((folder_name, instance_id))
                    logger.debug(f"Plugin ajouté pour retour: {folder_name}_{instance_id}")
                except Exception as e:
                    logger.error(f"Erreur lors de l'extraction des infos pour {plugin_id}: {e}")

            # Créer l'écran de configuration
            config_screen = PluginConfig(plugin_instances)

            # Préparer les configurations pour l'écran de config
            corrected_config = self._prepare_configs_for_return(self.plugins_config)

            # Préserver la configuration
            config_screen.current_config = corrected_config
            logger.debug(f"Configuration préservée: {len(corrected_config)} plugins")

            # Indiquer qu'on revient de l'écran d'exécution
            config_screen.returning_from_execution = True

            # Revenir à l'écran de configuration
            self.app.switch_screen(config_screen)
        except Exception as e:
            logger.error(f"Erreur lors du retour à l'écran de configuration: {e}")
            logger.error(traceback.format_exc())
            self.notify("Erreur lors du retour à la configuration", severity="error")

    def _prepare_configs_for_return(self, plugins_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prépare les configurations pour le retour à l'écran de configuration.

        Args:
            plugins_config: Configurations des plugins

        Returns:
            Dict[str, Any]: Configurations corrigées
        """
        corrected_config = {}

        for plugin_id, plugin_data in plugins_config.items():
            # Ignorer les séquences
            if isinstance(plugin_id, str) and plugin_id.startswith('__sequence__'):
                continue

            try:
                # Si déjà au bon format, l'utiliser directement
                if isinstance(plugin_data, dict) and 'config' in plugin_data:
                    corrected_config[plugin_id] = plugin_data
                else:
                    # Reconstruire la structure
                    parts = plugin_id.split('_')
                    plugin_name = parts[0]
                    instance_id = int(parts[-1]) if parts[-1].isdigit() else 0

                    # Récupérer les paramètres du plugin
                    plugin_folder = get_plugin_folder_name(plugin_name)
                    settings_path = os.path.join(
                        os.path.dirname(__file__), '..', '..', 'plugins',
                        plugin_folder, 'settings.yml'
                    )

                    plugin_settings = {}
                    try:
                        with open(settings_path, 'r', encoding='utf-8') as f:
                            from ruamel.yaml import YAML
                            yaml = YAML()
                            plugin_settings = yaml.load(f)
                    except Exception as e:
                        logger.error(f"Erreur lors du chargement des paramètres pour {plugin_id}: {e}")

                    remote_execution = plugin_data.get('remote_execution', False)

                    corrected_config[plugin_id] = {
                        'plugin_name': plugin_name,
                        'instance_id': instance_id,
                        'name': plugin_settings.get('name', plugin_name),
                        'show_name': plugin_settings.get('name', plugin_name),
                        'icon': plugin_settings.get('icon', '📦'),
                        'config': plugin_data,
                        'remote_execution': remote_execution
                    }
            except Exception as e:
                logger.error(f"Erreur lors de la correction de config pour {plugin_id}: {e}")

        return corrected_config