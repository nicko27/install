"""
Widget principal d'exécution de plugins.
"""

from typing import Dict
import traceback
import sys
import os
import json

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
        for plugin_id, config in self.plugins_config.items():
            # Récupérer le nom du plugin associé à cet ID
            plugin_name = config.get('plugin_name', '')
            if isinstance(plugin_name, str) and plugin_name.startswith('__sequence__'):
                # Extraire le nom de la séquence du nom du plugin
                sequence_file = plugin_name.replace('__sequence__', '')
                self.sequence_name = sequence_file.replace('.yml', '')
                logger.debug(f"Séquence détectée: {self.sequence_name}")
                break

        logger.debug(f"ExecutionWidget initialized with {len(self.plugins_config)} plugins: {list(self.plugins_config.keys())}")

    async def execute_plugin(self, plugin_id: str, config: dict) -> dict:
        """Exécute un plugin spécifique"""
        try:
            # Vérifier si c'est une séquence et ne pas l'exécuter
            if not isinstance(config, dict):
                logger.error(f"Configuration invalide pour le plugin {plugin_id}: {config}")
                return {
                    'success': False,
                    'output': f"Erreur: Configuration invalide pour le plugin {plugin_id}"
                }
            
            # Extraire les informations de base de la configuration
            plugin_name = config.get('plugin_name', '')
            if not plugin_name:
                # Si pas de nom de plugin, utiliser le dossier du plugin comme nom
                plugin_name = get_plugin_folder_name(str(plugin_id))
                logger.debug(f"Utilisation du dossier comme nom de plugin: {plugin_name}")
                
            # Récupérer la configuration du plugin
            plugin_config = {}
            # Si on a une clé 'config', l'utiliser
            if 'config' in config:
                plugin_config = config['config']
            else:
                # Sinon, copier toutes les clés sauf celles spéciales
                special_keys = {'plugin_name', 'instance_id', 'show_name', 'icon', 'remote_execution'}
                plugin_config = {k: v for k, v in config.items() if k not in special_keys}
            instance_id = config.get('instance_id', plugin_id)  # Si pas d'instance_id, utiliser plugin_id
            show_name = config.get('show_name', config.get('name', plugin_name))
            icon = config.get('icon', '📦')
                
            if isinstance(plugin_name, str) and plugin_name.startswith('__sequence__'):
                logger.warning(f"Tentative d'exécution d'une séquence comme plugin: {plugin_name}")
                return {
                    'success': False,
                    'output': f"Erreur: {plugin_name} est une séquence, pas un plugin."
                }

            # Récupérer le nom du plugin depuis son dossier
            folder_name = get_plugin_folder_name(plugin_name)
            logger.debug(f"Dossier du plugin {plugin_name} (ID: {instance_id}): {folder_name}")
            logger.debug(f"Configuration du plugin {plugin_name}: {plugin_config}")
            remote_execution = config.get('remote_execution', False)

            # Exécuter le plugin localement ou via SSH selon la configuration
            if remote_execution:
                logger.debug(f"Exécution SSH du plugin {plugin_id}")
                # Créer la configuration complète pour l'exécuteur SSH
                ssh_config = {
                    'plugin_name': folder_name,
                    'instance_id': instance_id,
                    'config': plugin_config,
                    'ssh_debug': plugin_config.get('ssh_debug', False)  # Récupérer ssh_debug de la config
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
            filtered_plugins = {}
            filtered_configs = {}
            sequence_plugin_ids = []
            
            # D'abord identifier tous les plugins de séquence principaux (pour les conserver)
            for plugin_id, config in self.plugins_config.items():
                plugin_name = config.get('plugin_name', '')
                if isinstance(plugin_name, str) and plugin_name.startswith('__sequence__'):
                    sequence_plugin_ids.append(plugin_id)
                    logger.debug(f"Plugin de séquence principal identifié: {plugin_id} -> {plugin_name}")
            
            # Créer une liste ordonnée des plugins pour préserver l'ordre d'exécution
            ordered_plugins = []
            
            # Parcourir tous les plugins disponibles
            for plugin_id, plugin in self.plugins.items():
                # Ignorer uniquement les plugins de séquence principaux, pas les plugins de la séquence
                if plugin_id in sequence_plugin_ids:
                    logger.debug(f"Ignoré plugin de séquence principal: {plugin_id}")
                    continue
                    
                # Vérifier si la configuration correspondante existe
                if plugin_id in self.plugins_config:
                    config = self.plugins_config[plugin_id]
                    
                    # Ajouter le plugin et sa configuration aux dictionnaires filtrés
                    filtered_plugins[plugin_id] = plugin
                    filtered_configs[plugin_id] = config
                    ordered_plugins.append(plugin_id)
                    logger.debug(f"Plugin ajouté aux filtres: {plugin_id}")
                else:
                    logger.warning(f"Configuration manquante pour le plugin {plugin_id}")

            total_plugins = len(filtered_plugins)
            logger.debug(f"Démarrage de l'exécution de {total_plugins} plugins (après filtrage des séquences)")
            logger.debug(f"Plugins disponibles: {list(filtered_plugins.keys())}")
            logger.debug(f"Plugins config: {list(filtered_configs.keys())}")
            logger.debug(f"Ordre d'exécution des plugins: {ordered_plugins}")
            logger.debug(f"Contenu détaillé des configurations filtrées: {json.dumps(filtered_configs, default=str, indent=2)}")
            executed = 0

            # Logs complets pour débogage
            logger.debug("=== Débogage de la séquence ===")
            logger.debug(f"self.plugins_config COMPLET: {json.dumps(self.plugins_config, default=str, indent=2)}")
            logger.debug(f"plugins.items() COMPLET: {[key for key in self.plugins.keys()]}")
            logger.debug(f"plugin_instance_counts DEBUG: {json.dumps({key: self.plugins_config[key].get('instance_id', '?') for key in self.plugins_config}, default=str)}")
            logger.debug("=== FIN Débogage de la séquence ===")
            
            # Ajouter un message de début d'exécution dans les logs
            await LoggerUtils.add_log(self, f"Démarrage de l'exécution de {total_plugins} plugins", level="info")

            # S'assurer que les logs sont visibles
            logs_container = self.query_one("#logs-container", ScrollableContainer)
            if logs_container and "hidden" in logs_container.classes:
                logs_container.remove_class("hidden")
                self.show_logs = True

            # Utiliser la liste ordonnée pour préserver l'ordre d'exécution
            for plugin_id in ordered_plugins:
                try:
                    logger.debug(f"Préparation de l'exécution de {plugin_id}")
                    plugin_widget = filtered_plugins[plugin_id]
                    config = filtered_configs[plugin_id]
                    plugin_name = plugin_widget.plugin_name
                    self.set_current_plugin(plugin_name)

                    # Initialiser la progression et le statut
                    try:
                        plugin_widget.update_progress(0.0, "En cours")
                    except Exception as e:
                        logger.warning(f"Impossible de mettre à jour la progression pour {plugin_id}: {e}")

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
                        try:
                            plugin_widget.set_status(status)
                        except Exception as status_error:
                            logger.warning(f"Impossible de mettre à jour le statut pour {plugin_id}: {status_error}")

                        # Vérifier que la méthode set_output existe
                        if hasattr(plugin_widget, 'set_output'):
                            try:
                                plugin_widget.set_output(output)
                            except Exception as output_error:
                                logger.warning(f"Impossible de définir la sortie pour {plugin_id}: {output_error}")
                        else:
                            logger.error(f"Le widget {plugin_id} n'a pas de méthode set_output")

                        # Ajouter un message de log explicite pour l'échec
                        if not success:
                            error_message = f"Échec du plugin {plugin_name}: {output}"
                            logger.error(error_message)
                            await LoggerUtils.add_log(self, error_message, level="error")
                            try:
                                plugin_widget.update_progress(100.0, "Échec")
                            except Exception as e:
                                logger.warning(f"Impossible de mettre à jour la progression finale pour {plugin_id}: {e}")
                        else:
                            try:
                                plugin_widget.update_progress(100.0, "Terminé")
                            except Exception as e:
                                logger.warning(f"Impossible de mettre à jour la progression finale pour {plugin_id}: {e}")
                            await LoggerUtils.add_log(self, f"Plugin {plugin_name} exécuté avec succès", level="success")
                    except Exception as exec_error:
                        logger.error(f"Erreur lors de l'exécution de {plugin_id}: {str(exec_error)}")
                        logger.error(f"Traceback complet: {traceback.format_exc()}")
                        try:
                            plugin_widget.set_status("error", f"Erreur: {str(exec_error)}")
                        except Exception as e:
                            logger.warning(f"Impossible de mettre à jour le statut d'erreur pour {plugin_id}: {e}")
                        try:
                            plugin_widget.update_progress(100.0, "Erreur")
                        except Exception as e:
                            logger.warning(f"Impossible de mettre à jour la progression d'erreur pour {plugin_id}: {e}")
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
                    try:
                        plugin_widget.set_status("erreur")
                    except Exception as status_error:
                        logger.warning(f"Impossible de mettre à jour le statut d'erreur pour {plugin_id}: {status_error}")
                    try:
                        plugin_widget.set_output(error_msg)
                    except Exception as output_error:
                        logger.warning(f"Impossible de définir la sortie d'erreur pour {plugin_id}: {output_error}")
                    try:
                        plugin_widget.update_progress(100.0, "Erreur")
                    except Exception as progress_error:
                        logger.warning(f"Impossible de mettre à jour la progression d'erreur pour {plugin_id}: {progress_error}")

                    # Ajouter l'erreur au rapport
                    if self.report_manager:
                        try:
                            instance_id = int(plugin_id.split('_')[-1])
                            self.report_manager.add_result(
                                plugin_name=plugin_name,
                                instance_id=instance_id,
                                success=False,
                                output=error_msg,
                                sequence_name=self.sequence_name
                            )
                        except Exception as report_error:
                            logger.error(f"Impossible d'ajouter l'erreur au rapport pour {plugin_id}: {report_error}")

                    # Continuer l'exécution même en cas d'erreur si l'option est activée
                    if not self.continue_on_error:
                        logger.warning(f"Arrêt de l'exécution après erreur sur {plugin_id}")
                        break
                    else:
                        logger.info(f"Poursuite de l'exécution malgré l'erreur sur {plugin_id} (continue_on_error=True)")

            # Ajouter un message de fin d'exécution dans les logs
            # Vérifier si tous les plugins ont été exécutés avec succès
            all_executed = executed == total_plugins

            # Vérifier si des erreurs ont été détectées dans les plugins
            has_errors = False
            for plugin_id, plugin_widget in self.plugins.items():
                if plugin_widget.status == "erreur":
                    has_errors = True
                    break

            # Déterminer si on est en mode SSH (remote_execution)
            is_remote = False
            for plugin_id, config in filtered_configs.items():
                if config.get('remote_execution', False):
                    is_remote = True
                    break

            # Ne pas afficher le message final en mode SSH, car il est déjà affiché par SSHExecutor
            if not is_remote:
                # Déterminer le niveau de log en fonction de l'exécution et des erreurs
                if has_errors:
                    level = "error"
                elif not all_executed:
                    level = "warning"
                else:
                    level = "success"
                if executed>1:
                    texte_plugin="plugins exécutés"
                else:
                    texte_plugin="plugin exécuté"
                # Construire le message
                message = f"Exécution terminée : {executed}/{total_plugins} {texte_plugin}"
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
        back_button = self.query_one("#back-button")
        if not start_button:
            logger.error("Bouton de démarrage introuvable")
            return

        try:
            # Démarrer l'exécution
            self.is_running = True
            logger.info("Démarrage de l'exécution")

            # Masquer les boutons Démarrer et Retour pendant l'exécution
            start_button.add_class("hidden")
            back_button.add_class("hidden")
            logger.debug("Boutons Démarrer et Retour masqués")

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

            # Réafficher les boutons après l'exécution
            start_button.remove_class("hidden")
            back_button.remove_class("hidden")
            logger.debug("Boutons Démarrer et Retour réaffichés après exécution")

        except Exception as e:
            logger.error(f"Erreur lors du démarrage de l'exécution : {str(e)}")
            logger.error(f"Traceback complet: {traceback.format_exc()}")
            error_msg = Message(
                type=MessageType.ERROR,
                content=f"Erreur lors du démarrage : {str(e)}"
            )
            logger.debug(f"Message d'erreur créé avec type={MessageType.ERROR} et content={str(e)}")
            await LoggerUtils.display_message(self, error_msg)

            # Réafficher les boutons en cas d'erreur
            start_button.remove_class("hidden")
            back_button.remove_class("hidden")
            logger.debug("Boutons Démarrer et Retour réaffichés après erreur")
        finally:
            self.is_running = False
            # Réinitialiser l'état du bouton retour
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
        # En-tête - Afficher le nom de la séquence si disponible
        header_text = "Exécution des plugins"
        if self.sequence_name:
            header_text = f"Exécution de la séquence: {self.sequence_name}"
        yield Header(name=header_text)

        # Liste des plugins
        with ScrollableContainer(id="plugins-list"):
            # Créer les conteneurs de plugins
            logger.debug(f"Création des conteneurs pour {len(self.plugins_config)} plugins")
            # Garder une trace des IDs de plugins déjà traités
            processed_plugins = set()
            
            # Faire une copie du dictionnaire pour éviter l'erreur "dictionary changed size during iteration"
            plugins_config_copy = self.plugins_config.copy()
            for plugin_id, config in plugins_config_copy.items():
                # Ignorer les plugins de type séquence mais conserver leur information
                plugin_name = config.get('plugin_name', '')
                if isinstance(plugin_name, str) and plugin_name.startswith('__sequence__'):
                    logger.debug(f"Ignoré le plugin de type séquence: {plugin_name}")
                    continue
                
                # Vérifier si ce plugin a déjà été traité
                if plugin_id in processed_plugins:
                    logger.debug(f"Plugin {plugin_id} déjà traité, ignoré")
                    continue
                processed_plugins.add(plugin_id)
                
                # Récupérer le nom du plugin depuis la configuration
                if not plugin_name:
                    plugin_name = get_plugin_folder_name(str(plugin_id))
                    logger.debug(f"Utilisation du dossier comme nom de plugin: {plugin_name}")
                
                # Déterminer le nom à afficher
                show_name = config.get('name', plugin_name)
                logger.debug(f"Nom d'affichage pour {plugin_name}: {show_name}")
                icon=config.get('icon', '📦')
                # Créer le conteneur pour ce plugin avec un ID unique
                plugin_container = PluginContainer(
                    plugin_id=plugin_id,
                    plugin_name=plugin_name,
                    plugin_show_name=show_name,
                    plugin_icon=icon
                )
                
                # Vérifier que le conteneur a bien été créé avec un ID unique
                if plugin_container.id:
                    # Stocker le conteneur
                    self.plugins[plugin_id] = plugin_container
                    # Ajouter le conteneur au DOM
                    yield plugin_container
                else:
                    logger.error(f"Impossible de créer un conteneur avec un ID unique pour {plugin_id}")

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

                            # Vérifier si ce conteneur existe déjà
                            if ip_plugin_id in self.plugins:
                                logger.debug(f"Conteneur déjà existant pour {ip_plugin_id}, ignoré")
                                continue

                            sanitized_id = self.sanitize_id(ip_plugin_id)

                            # Créer un conteneur avec l'IP dans le nom
                            ip_show_name = f"{show_name} ({ip})"
                            container = PluginContainer(sanitized_id, plugin_name, ip_show_name, icon)

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
                        # Vérifier si un conteneur d'erreur existe déjà
                        if plugin_id in self.plugins:
                            logger.debug(f"Conteneur d'erreur déjà existant pour {plugin_id}, ignoré")
                        else:
                            # Aucune IP valide, créer un conteneur d'erreur
                            sanitized_id = self.sanitize_id(plugin_id)
                            container = PluginContainer(sanitized_id, plugin_name, f"{show_name} (Aucune IP valide)", icon)
                            self.plugins[plugin_id] = container
                            logger.debug(f"Conteneur d'erreur ajouté pour {plugin_id}: Aucune IP valide")
                            yield container
                else:
                    # Vérifier si le conteneur existe déjà
                    if plugin_id in self.plugins:
                        logger.debug(f"Conteneur déjà existant pour {plugin_id}, ignoré")
                    else:
                        # Plugin normal (non-SSH ou SSH avec une seule IP)
                        sanitized_id = self.sanitize_id(plugin_id)
                        container = PluginContainer(sanitized_id, plugin_name, show_name, icon)

                        # Si c'est un plugin SSH avec une seule IP, stocker l'IP
                        if ssh_ips and not ('*' in ssh_ips or ',' in ssh_ips):
                            container.target_ip = ssh_ips.strip()
                            
                        # Stocker le conteneur et le retourner
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
                # Démarrer l'exécution sans manipuler les classes ici (déplacé vers start_execution)
                await self.start_execution()
            elif button_id == "back-button":
                # Marquer que le bouton retour a été cliqué
                self.back_button_clicked = True
                logger.debug("Bouton retour cliqué, activation du bouton démarrer")

                # Import ici pour éviter les imports circulaires
                from ..config_screen.config_screen import PluginConfig
                from ..config_screen.config_manager import ConfigManager

                # Extraire les infos de plugin_id
                plugin_instances = []
                for plugin_id in self.plugins_config.keys():
                    # Récupérer la configuration du plugin
                    config = self.plugins_config.get(plugin_id, {})
                    if not isinstance(config, dict):
                        logger.error(f"Configuration invalide pour le plugin {plugin_id}")
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

                # Convertir le format de configuration pour qu'il soit compatible avec PluginConfig
                corrected_config = {}
                for plugin_id, plugin_data in self.plugins_config.items():
                    # Ignorer les séquences
                    if plugin_id.startswith('__sequence__'):
                        continue

                    try:
                        # Si c'est déjà au bon format, l'utiliser directement
                        if isinstance(plugin_data, dict) and 'config' in plugin_data:
                            corrected_config[plugin_id] = plugin_data
                            logger.debug(f"Config au bon format pour {plugin_id}")
                        else:
                            # Sinon, construire la structure attendue
                            plugin_name = plugin_id.split('_')[0]
                            instance_id = int(plugin_id.split('_')[-1])

                            # Déterminer les attributs du plugin
                            plugin_folder = get_plugin_folder_name(plugin_id)
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
                            logger.debug(f"Config reconstruite pour {plugin_id}")
                    except Exception as e:
                        logger.error(f"Erreur lors de la conversion de config pour {plugin_id}: {e}")

                # Préserver la configuration convertie
                config_screen.current_config = corrected_config
                logger.debug(f"Configuration préservée: {len(corrected_config)} plugins")

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