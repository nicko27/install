"""
Widget principal d'exécution de plugins.
"""

from typing import Dict
import traceback
import sys

from textual.app import ComposeResult
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
    """Widget principal d'exécution des plugins"""

    # État d'exécution
    is_running = reactive(False)
    continue_on_error = reactive(False)
    show_logs = reactive(True)  # Logs visibles par défaut
    back_button_clicked = reactive(False)  # Pour suivre si le bouton retour a été cliqué

    def __init__(self, plugins_config: dict = None):
        """Initialise le widget avec la configuration des plugins"""
        super().__init__()
        self.plugins: Dict[str, PluginContainer] = {}
        self.plugins_config = plugins_config or {}
        self._current_plugin = None
        self._total_plugins = 0
        self._executed_plugins = 0
        self.report_manager = None  # Gestionnaire de rapports
        self.sequence_name = None   # Nom de la séquence en cours
        self._app_ref = None  # Référence à l'application, sera définie lors du montage

        # Extraire le nom de la séquence si présent dans la configuration
        for plugin_id in self.plugins_config.keys():
            if plugin_id.startswith('__sequence__'):
                # Extraire le nom de la séquence du plugin_id
                sequence_file = plugin_id.replace('__sequence__', '')
                self.sequence_name = sequence_file.replace('.yml', '')
                logger.debug(f"Séquence détectée: {self.sequence_name}")
                break

        logger.debug(f"ExecutionWidget initialized with {len(self.plugins_config)} plugins: {list(self.plugins_config.keys())}")

    async def execute_plugin(self, plugin_id: str, config: dict) -> dict:
        """Exécute un plugin spécifique"""
        try:
            # Vérifier si c'est une séquence et ne pas l'exécuter
            if plugin_id.startswith('__sequence__'):
                logger.warning(f"Tentative d'exécution d'une séquence comme plugin: {plugin_id}")
                return {
                    'success': False,
                    'output': f"Erreur: {plugin_id} est une séquence, pas un plugin."
                }

            # Récupérer le nom du plugin depuis son dossier
            folder_name = get_plugin_folder_name(plugin_id)
            logger.debug(f"Dossier du plugin {plugin_id}: {folder_name}")
            logger.debug(f"Configuration du plugin {plugin_id}: {config}")
            remote_execution = config.get('remote_execution', False)
            
            # Exécuter le plugin localement ou via SSH selon la configuration
            if remote_execution:
                logger.debug(f"Exécution SSH du plugin {plugin_id}")
                # Créer la configuration complète pour l'exécuteur SSH
                ssh_config = {
                    'plugin_name': folder_name,
                    'instance_id': 0,
                    'config': config,
                    'ssh_debug': config.get('ssh_debug', False)  # Récupérer ssh_debug de la config
                }
                executor = SSHExecutor(ssh_config)
                logger.debug(f"Exécuteur SSH créé pour {plugin_id} avec la configuration: {ssh_config}")
            else:
                logger.debug(f"Exécution locale du plugin {plugin_id}")
                executor = LocalExecutor(self.app if self._app_ref is None else self._app_ref)
                logger.debug(f"Exécuteur local créé pour {plugin_id}")

            # Vérifier que la méthode execute_plugin existe
            if not hasattr(executor, 'execute_plugin'):
                logger.error(f"L'exécuteur {type(executor).__name__} n'a pas de méthode execute_plugin")
                return {
                    'success': False,
                    'output': f"Erreur: L'exécuteur {type(executor).__name__} n'a pas de méthode execute_plugin"
                }

            # Exécuter le plugin
            try:
                plugin_widget = self.plugins.get(plugin_id)
                success, output = await executor.execute_plugin(plugin_widget,folder_name, config)
                return {
                    'success': success,
                    'output': output
                }
            except Exception as exec_error:
                error_msg = str(exec_error)
                target_ip = getattr(plugin_widget, 'target_ip', None) if plugin_widget else None

                # Log détaillé avec l'IP si disponible
                if target_ip:
                    logger.error(f"Erreur lors de l'exécution du plugin {plugin_id} sur {target_ip}: {error_msg}")
                else:
                    logger.error(f"Erreur lors de l'exécution du plugin {plugin_id}: {error_msg}")

                logger.error(f"Traceback: {traceback.format_exc()}")

                # Ajouter un message d'erreur dans les logs de l'interface
                try:
                    if target_ip:
                        await LoggerUtils.add_log(
                            self.app if self._app_ref is None else self._app_ref,
                            f"Erreur d'exécution du plugin {folder_name}: {error_msg}",
                            level="error",
                            target_ip=target_ip
                        )
                    else:
                        await LoggerUtils.add_log(
                            self.app if self._app_ref is None else self._app_ref,
                            f"Erreur d'exécution du plugin {folder_name}: {error_msg}",
                            level="error"
                        )
                except Exception as log_error:
                    logger.error(f"Erreur lors de l'ajout du message d'erreur aux logs: {log_error}")

                # Message d'erreur plus détaillé pour l'utilisateur
                if target_ip:
                    output_msg = f"Erreur d'exécution sur {target_ip}: {error_msg}"
                else:
                    output_msg = f"Erreur d'exécution: {error_msg}"

                return {
                    'success': False,
                    'output': output_msg
                }

        except Exception as e:
            logger.error(f"Erreur exécution plugin {plugin_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'output': f"Erreur: {str(e)}"
            }

    async def run_plugins(self):
        """Exécute les plugins de façon séquentielle"""
        try:
            # Filtrer les plugins de type séquence
            filtered_plugins = {plugin_id: plugin for plugin_id, plugin in self.plugins.items()
                              if not plugin_id.startswith('__sequence__')}

            # Filtrer également les configurations des plugins
            filtered_configs = {plugin_id: config for plugin_id, config in self.plugins_config.items()
                              if not plugin_id.startswith('__sequence__')}

            total_plugins = len(filtered_plugins)
            logger.debug(f"Démarrage de l'exécution de {total_plugins} plugins (après filtrage des séquences)")
            logger.debug(f"Plugins disponibles: {list(filtered_plugins.keys())}")
            logger.debug(f"Plugins config: {list(filtered_configs.keys())}")
            logger.debug(f"Contenu des configurations filtrées: {filtered_configs}")
            executed = 0

            # Ajouter un message de début d'exécution dans les logs
            await LoggerUtils.add_log(self, f"Démarrage de l'exécution de {total_plugins} plugins", level="info")

            # S'assurer que les logs sont visibles
            logs_container = self.query_one("#logs-container", ScrollableContainer)
            if logs_container and "hidden" in logs_container.classes:
                logs_container.remove_class("hidden")
                self.show_logs = True

            for plugin_id, plugin_widget in filtered_plugins.items():
                try:
                    logger.debug(f"Préparation de l'exécution de {plugin_id}")
                    config = filtered_configs[plugin_id]
                    plugin_name = plugin_widget.plugin_name
                    self.set_current_plugin(plugin_name)

                    # Initialiser la progression et le statut
                    plugin_widget.update_progress(0.0, "Démarrage...")

                    # Exécuter le plugin
                    try:
                        logger.debug(f"Début de l'exécution du plugin {plugin_id} avec config: {config}")
                        # Mettre à jour la progression globale pour indiquer le début de l'exécution du plugin
                        self.update_global_progress(executed / total_plugins)

                        result = await self.execute_plugin(plugin_id, config)
                        logger.debug(f"Résultat brut de l'exécution du plugin {plugin_id}: {result}")
                        success = result.get('success', False)
                        output = result.get('output', '')
                        logger.debug(f"Succès: {success}, Sortie (début): {output[:100]}..." if len(str(output)) > 100 else f"Succès: {success}, Sortie: {output}")

                        # Mettre à jour le statut du plugin
                        status = "success" if success else "error"
                        plugin_widget.set_status(status)

                        # Vérifier que la méthode set_output existe
                        if hasattr(plugin_widget, 'set_output'):
                            plugin_widget.set_output(output)
                        else:
                            logger.error(f"Le widget {plugin_id} n'a pas de méthode set_output")

                        # Ajouter un message de log explicite pour l'échec
                        if not success:
                            error_message = f"Échec du plugin {plugin_name}: {output}"
                            logger.error(error_message)
                            await LoggerUtils.add_log(self, error_message, level="error")
                            plugin_widget.update_progress(100.0, "Échec")
                        else:
                            plugin_widget.update_progress(100.0, "Terminé")
                            await LoggerUtils.add_log(self, f"Plugin {plugin_name} exécuté avec succès", level="success")
                    except Exception as exec_error:
                        logger.error(f"Erreur lors de l'exécution de {plugin_id}: {str(exec_error)}")
                        logger.error(f"Traceback complet: {traceback.format_exc()}")
                        plugin_widget.set_status("error", f"Erreur: {str(exec_error)}")
                        plugin_widget.update_progress(100.0, "Erreur")
                        success = False
                        output = f"Erreur: {str(exec_error)}"

                    # Ajouter au rapport si activé
                    if self.report_manager:
                        # Extraire l'ID d'instance du plugin_id (dernier nombre)
                        instance_id = int(plugin_id.split('_')[-1])

                        self.report_manager.add_result(
                            plugin_name=plugin_name,
                            instance_id=instance_id,
                            success=success,
                            output=output,
                            sequence_name=self.sequence_name
                        )

                    executed += 1
                    self.update_global_progress(executed / total_plugins * 100)

                    # En cas d'erreur, vérifier si on continue
                    if not success and not self.continue_on_error:
                        logger.warning(f"Arrêt de l'exécution après erreur sur {plugin_name}")
                        break

                except Exception as e:
                    error_msg = f"Erreur lors de l'exécution de {plugin_id}: {str(e)}"
                    logger.error(error_msg)
                    logger.error(f"Traceback complet: {traceback.format_exc()}")
                    plugin_widget.set_status("erreur")
                    plugin_widget.set_output(error_msg)
                    plugin_widget.update_progress(100.0, "Erreur")

                    # Ajouter l'erreur au rapport
                    if self.report_manager:
                        instance_id = int(plugin_id.split('_')[-1])
                        self.report_manager.add_result(
                            plugin_name=plugin_name,
                            instance_id=instance_id,
                            success=False,
                            output=error_msg,
                            sequence_name=self.sequence_name
                        )

                    if not self.continue_on_error:
                        break

            # Ajouter un message de fin d'exécution dans les logs
            # Vérifier si tous les plugins ont été exécutés avec succès
            all_executed = executed == total_plugins
            
            # Vérifier si des erreurs ont été détectées dans les plugins
            has_errors = False
            for plugin_id, plugin_widget in self.plugins.items():
                if plugin_widget.status == "erreur":
                    has_errors = True
                    break
            
            # Déterminer le niveau de log en fonction de l'exécution et des erreurs
            if has_errors:
                level = "error"
            elif not all_executed:
                level = "warning"
            else:
                level = "success"
            
            # Construire le message
            message = f"Exécution terminée : {executed}/{total_plugins} plugins exécutés"
            if has_errors:
                message += " (des erreurs ont été détectées)"
            elif not all_executed:
                message += " (certains plugins n'ont pas été exécutés)"
                
            await LoggerUtils.add_log(self, message, level=level)

        except Exception as e:
            logger.error(f"Erreur globale lors de l'exécution : {str(e)}")
            # Ajouter un message d'erreur dans les logs
            await LoggerUtils.add_log(self, f"Erreur lors de l'exécution : {str(e)}", level="error")
            raise

    async def start_execution(self):
        """Démarrage de l'exécution des plugins"""
        # Vérifier si une exécution est déjà en cours
        if self.is_running:
            logger.debug("Exécution déjà en cours, ignoré")
            return

        start_button = self.query_one("#start-button")
        if not start_button:
            logger.error("Bouton de démarrage introuvable")
            return

        try:
            # Démarrer l'exécution
            self.is_running = True
            logger.info("Démarrage de l'exécution")
            start_button.disabled = True
            logger.debug("Bouton désactivé")

            # Réinitialiser l'interface
            self.update_global_progress(0)
            self.set_current_plugin("aucun")
            await LoggerUtils.clear_logs(self)

            # Exécuter les plugins
            await self.run_plugins()

            # Notifier la fin de l'exécution
            logger.debug("Notification de fin d'exécution")
            if hasattr(self.app.screen, 'on_execution_completed'):
                await self.app.screen.on_execution_completed()

        except Exception as e:
            logger.error(f"Erreur lors du démarrage de l'exécution : {str(e)}")
            logger.error(f"Traceback complet: {traceback.format_exc()}")
            error_msg = Message(
                type=MessageType.ERROR,
                content=f"Erreur lors du démarrage : {str(e)}"
            )
            logger.debug(f"Message d'erreur créé avec type={MessageType.ERROR} et content={str(e)}")
            await LoggerUtils.display_message(self, error_msg)

            # Réactiver le bouton en cas d'erreur
            start_button.disabled = False
            logger.debug("Bouton réactivé après erreur")
        finally:
            self.is_running = False
            # Réactiver le bouton
            start_button.disabled = False

            # Réinitialiser l'état du bouton retour et masquer le bouton démarrer
            self.back_button_clicked = False
            logger.debug("Réinitialisation de back_button_clicked à False après exécution")


    def update_global_progress(self, progress: float):
        """Mise à jour de la progression globale"""
        logger.debug(f"update_global_progress appelé avec progress={progress}")
        try:
            # Try to find the progress bar
            try:
                progress_bar = self.query_one("#global-progress")
                if progress_bar:
                    logger.debug(f"Mise à jour de la barre de progression globale: {progress * 100}%")
                    progress_bar.update(total=100.0, progress=progress * 100)
                else:
                    logger.debug("Barre de progression globale non trouvée par query")
            except Exception as query_error:
                # If we can't find it by query, try to access it directly via DOM
                logger.debug(f"Impossible de trouver la barre de progression par query: {str(query_error)}")
                # Try to create it if it doesn't exist
                button_container = self.query_one("#button-container")
                if button_container:
                    # Check if it already exists
                    existing_bars = [w for w in button_container.children if getattr(w, "id", "") == "global-progress"]
                    if existing_bars:
                        existing_bars[0].update(total=100.0, progress=progress * 100)
                    else:
                        logger.debug("Création d'une nouvelle barre de progression")
                        # Create a new progress bar
                        from textual.widgets import ProgressBar
                        new_bar = ProgressBar(id="global-progress", show_eta=False)
                        new_bar.total = 100.0
                        new_bar.progress = progress * 100
                        button_container.mount(new_bar)
        except Exception as e:
            # Log the error but don't crash if the progress bar isn't found
            logger.error(f"Impossible de mettre à jour la progression: {str(e)}")

    def set_current_plugin(self, plugin_name: str):
        """Met à jour l'affichage du plugin courant et scrolle vers lui"""
        try:
            # Mettre à jour le label global si possible
            try:
                progress_label = self.query_one("#global-progress-label")
                if progress_label:
                    progress_label.update(f"Plugin: {plugin_name}")
            except Exception as e:
                logger.debug(f"Impossible de mettre à jour le label de progression: {str(e)}")

            # Trouver le plugin en cours et scroller vers lui
            try:
                plugins_list = self.query_one("#plugins-list")
                if plugins_list and plugin_name != "aucun":
                    for plugin_id, plugin in self.plugins.items():
                        if plugin.plugin_name == plugin_name:
                            # Scroller vers le plugin
                            plugin.scroll_visible()
                            break
            except Exception as e:
                logger.debug(f"Impossible de scroller vers le plugin {plugin_name}: {str(e)}")
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du plugin courant: {str(e)}")

    def action_toggle_logs(self) -> None:
        """Afficher/Masquer les logs (appelé par le raccourci clavier ou le bouton)"""
        LoggerUtils.toggle_logs(self)

    # Méthode pour compatibilité avec loggers existants
    async def display_log(self, message, level="info"):
        """Méthode pour compatibilité avec anciens systèmes de logs"""
        await LoggerUtils.add_log(self, message, level)

    def sanitize_id(self, id_string):
        """Sanitize a string to be used as an ID by removing invalid characters"""
        # Replace dots, spaces and other invalid characters with underscores
        return ''.join(c if c.isalnum() or c in '-_' else '_' for c in id_string)

    def compose(self) -> ComposeResult:
        """Création de l'interface"""
        # En-tête - Afficher seulement 'Exécution des plugins' sans le nom de la séquence
        yield Header(name="Exécution des plugins")

        # Liste des plugins
        with ScrollableContainer(id="plugins-list"):
            # Créer les conteneurs de plugins
            logger.debug(f"Création des conteneurs pour {len(self.plugins_config)} plugins")
            # Faire une copie du dictionnaire pour éviter l'erreur "dictionary changed size during iteration"
            plugins_config_copy = self.plugins_config.copy()
            for plugin_id, config in plugins_config_copy.items():
                # Ignorer les plugins de type séquence (commençant par __sequence__)
                if plugin_id.startswith('__sequence__'):
                    logger.debug(f"Ignoré le plugin de type séquence: {plugin_id}")
                    continue

                # Récupérer le nom du plugin depuis son dossier
                folder_name = get_plugin_folder_name(plugin_id)
                plugin_name = config.get('plugin_name', folder_name)
                plugin_icon = config.get('icon', '📦')
                plugin_show_name = config.get('name', plugin_name)
                logger.debug(f"Création du conteneur pour {plugin_id}: nom={plugin_name}, affichage={plugin_show_name}")

                # Vérifier si c'est un plugin SSH avec plusieurs IPs
                plugin_config = config.get('config', {})
                ssh_ips = plugin_config.get('ssh_ips', '')
                ssh_exception_ips = plugin_config.get('ssh_exception_ips', '')

                # Si c'est un plugin SSH avec des IPs
                if ssh_ips and '*' in ssh_ips or ',' in ssh_ips:
                    # Obtenir la liste des IPs cibles
                    target_ips = get_target_ips(ssh_ips, ssh_exception_ips)
                    logger.debug(f"Plugin SSH {plugin_id} avec {len(target_ips)} IPs cibles: {target_ips}")

                    if target_ips:
                        # Créer un conteneur pour chaque IP
                        for ip in target_ips:
                            # Créer un ID unique pour ce plugin+IP
                            ip_plugin_id = f"{plugin_id}_{ip.replace('.', '_')}"
                            sanitized_id = self.sanitize_id(ip_plugin_id)

                            # Créer un conteneur avec l'IP dans le nom
                            ip_show_name = f"{plugin_show_name} ({ip})"
                            container = PluginContainer(sanitized_id, plugin_name, ip_show_name, plugin_icon)

                            # Stocker l'IP cible dans le conteneur pour l'exécution
                            container.target_ip = ip

                            # Ajouter le conteneur à la liste des plugins
                            self.plugins[ip_plugin_id] = container

                            # Créer une copie de la configuration pour cette IP spécifique
                            ip_config = config.copy()
                            # Ajouter cette configuration à plugins_config pour qu'elle soit disponible lors de l'exécution
                            self.plugins_config[ip_plugin_id] = ip_config

                            logger.debug(f"Conteneur ajouté pour {ip_plugin_id}: {ip_show_name}")

                            yield container
                    else:
                        # Aucune IP valide, créer un conteneur d'erreur
                        sanitized_id = self.sanitize_id(plugin_id)
                        container = PluginContainer(sanitized_id, plugin_name, f"{plugin_show_name} (Aucune IP valide)", plugin_icon)
                        self.plugins[plugin_id] = container
                        logger.debug(f"Conteneur d'erreur ajouté pour {plugin_id}: Aucune IP valide")
                        yield container
                else:
                    # Plugin normal (non-SSH ou SSH avec une seule IP)
                    sanitized_id = self.sanitize_id(plugin_id)
                    container = PluginContainer(sanitized_id, plugin_name, plugin_show_name, plugin_icon)

                    # Si c'est un plugin SSH avec une seule IP, stocker l'IP
                    if ssh_ips and not ('*' in ssh_ips or ',' in ssh_ips):
                        container.target_ip = ssh_ips.strip()

                    self.plugins[plugin_id] = container
                    logger.debug(f"Conteneur ajouté pour {plugin_id}: {plugin_name}")
                    yield container

        # Zone des logs (visible par défaut)
        with Horizontal(id="logs"):
            with ScrollableContainer(id="logs-container", classes=""):
                yield Static("", id="logs-text")

        with Horizontal(id="button-container"):
            yield Button("Retour", id="back-button", variant="error")
            yield Checkbox("Continuer en cas d'erreur", id="continue-on-error", value=True)
            yield Label("Progression globale", id="global-progress-label")
            # Ensure the progress bar is properly initialized with default values
            progress_bar = ProgressBar(id="global-progress", show_eta=False)
            progress_bar.total = 100.0
            progress_bar.progress = 0.0
            yield progress_bar
            # Masquer le bouton démarrer par défaut
            yield Button("Démarrer", id="start-button", variant="primary")

        yield Footer()

    async def on_mount(self) -> None:
        """Appelé au montage initial du widget"""
        # Récupérer la référence à l'application
        # Dans Textual, self.app est déjà disponible, on la stocke dans notre variable
        self._app_ref = self.app
        logger.debug(f"ExecutionWidget on_mount: app={self._app_ref}")

        # Appeler initialize_ui après le rafraîchissement du DOM
        # call_after_refresh ne retourne pas un awaitable, donc pas de await
        self.call_after_refresh(self.initialize_ui)

    async def initialize_ui(self):
        """Initialise l'interface après que le DOM soit complètement monté"""
        try:
            # Initialisation basique
            self.update_global_progress(0)
            self.set_current_plugin("aucun")

            # S'assurer que les logs sont visibles
            logs_container = self.query_one("#logs-container", ScrollableContainer)
            if logs_container and "hidden" in logs_container.classes:
                logs_container.remove_class("hidden")
                self.show_logs = True

            # Gérer l'affichage du bouton démarrer en fonction de l'état de back_button_clicked
            start_button = self.query_one("#start-button")
            if start_button:
                if self.back_button_clicked and "hidden" in start_button.classes:
                    # Si le bouton retour a été cliqué, afficher le bouton démarrer
                    start_button.remove_class("hidden")
                    logger.debug("Bouton démarrer affiché (back_button_clicked=True)")

            # Ajouter un message initial dans les logs
            await LoggerUtils.add_log(self, "Initialisation de l'interface terminée", level="info")

            # Initialiser l'état de la checkbox
            self.continue_on_error = True  # True par défaut

            # Initialiser l'affichage des logs
            await LoggerUtils.clear_logs(self)
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de l'UI: {str(e)}")


    async def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Gestion du changement d'état de la checkbox"""
        if event.checkbox.id == "continue-on-error":
            self.continue_on_error = event.value
            logger.debug(f"Option 'continuer en cas d'erreur' changée à: {self.continue_on_error}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Gestion des clics sur les boutons"""
        button_id = event.button.id
        logger.debug(f"Clic sur le bouton {button_id}")

        if not button_id:
            logger.warning("Bouton sans identifiant détecté")
            return

        try:
            if button_id == "start-button" and not event.button.disabled:
                start_button = self.query_one("#start-button")
                start_button.add_class("hidden")
                # Vérifier si le bouton n'est pas déjà désactivé
                await self.start_execution()
            elif button_id == "back-button":
                # Marquer que le bouton retour a été cliqué
                self.back_button_clicked = True
                logger.debug("Bouton retour cliqué, activation du bouton démarrer")

                # Afficher le bouton démarrer
                start_button = self.query_one("#start-button")
                if start_button and "hidden" in start_button.classes:
                    start_button.remove_class("hidden")
                    logger.debug("Bouton démarrer affiché")

                # Import ici pour éviter les imports circulaires
                from ..config_screen.config_screen import PluginConfig
                from ..config_screen.config_manager import ConfigManager

                # Extraire les infos de plugin_id
                plugin_instances = []
                for plugin_id in self.plugins_config.keys():
                    # Récupérer le dossier du plugin
                    folder_name = get_plugin_folder_name(plugin_id)
                    # Extraire l'instance ID (dernier nombre)
                    instance_id = int(plugin_id.split('_')[-1])
                    # Ajouter le tuple (nom_plugin, instance_id)
                    plugin_instances.append((folder_name, instance_id))

                # Récupérer la configuration actuelle pour la préserver
                current_config = self.plugins_config.copy()
                
                # Créer l'écran de configuration avec la configuration actuelle
                config_screen = PluginConfig(plugin_instances)
                
                # Préserver la configuration actuelle
                config_screen.current_config = current_config
                
                # Indiquer que nous revenons de l'écran d'exécution pour charger la configuration
                config_screen.returning_from_execution = True
                
                # Revenir à l'écran de configuration
                self.app.switch_screen(config_screen)
            elif button_id == "toggle-logs-button":
                # Afficher/Masquer les logs
                self.action_toggle_logs()
            elif button_id == "quit-button":
                self.app.exit()

        except Exception as e:
            logger.error(f"Erreur lors du traitement du clic sur {button_id} : {str(e)}")
            # En cas d'erreur sur le bouton start, on le réactive
            if button_id == "start-button":
                event.button.disabled = False
                logger.debug("Bouton réactivé après erreur")
            # Propager l'erreur pour le traitement global
            raise