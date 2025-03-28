from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Label, Header, Footer, Button
import sys
import traceback
from ..utils.logging import get_logger
from ..execution_screen.execution_screen import ExecutionScreen

from .plugin_card import PluginCard
from .selected_plugins_panel import SelectedPluginsPanel
from .plugin_utils import load_plugin_info
from .sequence_handler import SequenceHandler
from .template_handler import TemplateHandler

logger = get_logger('choice_screen')

class Choice(App):
    """Application principale pour la sélection des plugins"""
    BINDINGS = [
        ("escape", "quit", "Quitter"),  # Raccourci pour quitter l'application
    ]

    CSS_PATH = "../styles/choice.tcss"  # Chemin vers le fichier CSS

    def __init__(self):
        super().__init__()
        logger.debug("Initialisation de l'application Choice")

        # Initialisation des gestionnaires
        self.sequence_handler = SequenceHandler()
        self.template_handler = TemplateHandler()
        self.report_manager = None  # Initialisé si besoin

        # État de l'application
        self.selected_plugins = []   # Liste des tuples (plugin_name, instance_id)
        self.instance_counter = {}   # Compteur d'instances par plugin
        self.plugin_templates = {}   # Templates par plugin
        self.sequence_file = None    # Fichier de séquence passé en argument
        self.auto_execute = False    # Mode exécution automatique
        self.report_file = None      # Fichier pour le rapport d'exécution
        self.report_format = 'csv'   # Format du rapport (csv ou txt)

        # Vérifier les arguments de ligne de commande
        if len(sys.argv) > 1:
            sequence_path = sys.argv[1]
            sequence_file = Path(sequence_path)
            if sequence_file.exists():
                logger.info(f"Fichier de séquence détecté : {sequence_path}")
                self.sequence_file = sequence_file
                # Vérifier si mode auto-exécution
                if len(sys.argv) > 2 and sys.argv[2] == '--auto':
                    self.auto_execute = True
                    logger.info("Mode auto-exécution activé")

    def compose(self) -> ComposeResult:
        yield Header()  # En-tête de l'application
        with Horizontal(id="main-content"):
            with Vertical(id="plugins-column"):
                yield Label("Sélectionnez vos plugins", classes="section-title")
                with ScrollableContainer(id="plugin-cards"):
                    yield from self.create_plugin_cards()
            yield SelectedPluginsPanel(id="selected-plugins")
        with Horizontal(id="button-container"):
            yield Button("Configurer", id="configure_selected", variant="primary")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Gère les clics sur les boutons de l'application"""
        logger.debug(f"Bouton cliqué : {event.button.id}")
        if event.button.id == "configure_selected":
            await self.action_configure_selected()
        elif event.button.id == "quit":
            if self.auto_execute:
                # Sauvegarder le rapport avant de quitter
                self.save_execution_report()
            self.exit()

    def create_plugin_cards(self) -> list:
        """Crée les cartes de plugins et de séquences dynamiquement"""
        plugin_cards = []
        plugins_dir = Path('plugins')

        try:
            # Récupérer les plugins valides
            valid_plugins = []
            for plugin_path in plugins_dir.iterdir():
                if not plugin_path.is_dir():
                    continue

                settings_path = plugin_path / 'settings.yml'
                exec_py_path = plugin_path / 'exec.py'
                exec_bash_path = plugin_path / 'exec.bash'

                if (settings_path.exists() and
                    (exec_py_path.exists() or exec_bash_path.exists())):
                    try:
                        plugin_info = load_plugin_info(plugin_path.name)
                        display_name = plugin_info.get('name', plugin_path.name)
                        valid_plugins.append((display_name, plugin_path.name))

                        # Charger les templates du plugin
                        self.plugin_templates[plugin_path.name] = \
                            self.template_handler.get_plugin_templates(plugin_path.name)
                    except Exception as e:
                        logger.error(f"Erreur chargement plugin {plugin_path.name} : {e}")

            # Ajouter les séquences comme plugins spéciaux
            sequences = self.sequence_handler.get_available_sequences()
            for seq in sequences:
                # Ajouter directement la séquence sans préfixe dans le nom d'affichage
                valid_plugins.append(
                    (seq['name'], f"__sequence__{seq['file_name']}")
                )

            # Trier et créer les cartes
            valid_plugins.sort(key=lambda x: x[0].lower())
            for _, plugin_name in valid_plugins:
                plugin_cards.append(PluginCard(plugin_name))

            # Si une séquence est spécifiée en argument, la charger automatiquement
            if self.sequence_file:
                self.load_sequence(self.sequence_file)
                if self.auto_execute:
                    self.action_configure_selected()

            return plugin_cards
        except Exception as e:
            logger.error(f"Erreur découverte plugins : {e}")
            return []

    def load_sequence(self, sequence_path: Path) -> None:
        """Charge une séquence depuis un fichier YAML"""
        sequence = self.sequence_handler.load_sequence(sequence_path)
        if not sequence:
            return

        try:
            # Nous ajoutons toujours les plugins de la séquence à ceux déjà sélectionnés

            # Ajouter la séquence elle-même à la liste des plugins sélectionnés
            sequence_name = f"__sequence__{sequence_path.name}"
            self.selected_plugins.append((sequence_name, len(self.selected_plugins)))

            # Ajouter chaque plugin de la séquence
            for plugin_config in sequence['plugins']:
                plugin_name = plugin_config['name']
                
                # Récupérer la configuration
                config = {}
                if 'config' in plugin_config:
                    config = plugin_config['config']
                elif 'variables' in plugin_config:  # Rétrocompatibilité
                    config = plugin_config['variables']
                logger.debug(f"Configuration pour {plugin_name}: {config}")

                # Vérifier si un template est spécifié
                if 'template' in plugin_config:
                    template_name = plugin_config['template']
                    if template_name in self.plugin_templates.get(plugin_name, {}):
                        logger.debug(f"Application du template {template_name} pour {plugin_name}")
                        plugin_config = self.template_handler.apply_template(
                            plugin_name, template_name, plugin_config
                        )

                # Incrémenter le compteur d'instance
                if plugin_name not in self.instance_counter:
                    self.instance_counter[plugin_name] = 0
                self.instance_counter[plugin_name] += 1
                
                # Générer l'ID unique de l'instance
                instance_id = self.instance_counter[plugin_name]

                # Ajouter le plugin à la sélection avec sa configuration
                self.selected_plugins.append((plugin_name, instance_id, config))

            # Mettre à jour le panneau de sélection
            panel = self.query_one("#selected-plugins", SelectedPluginsPanel)
            panel.update_plugins(self.selected_plugins)

            logger.info(f"Séquence chargée : {len(sequence['plugins'])} plugins")

        except Exception as e:
            logger.error(f"Erreur lors de l'application de la séquence : {e}")

    def on_plugin_card_plugin_selection_changed(self, message: PluginCard.PluginSelectionChanged) -> None:
        """Gère les changements de sélection des plugins et séquences"""
        logger.debug(f"Changement sélection: {message.plugin_name} -> {message.selected}")

        # Vérifier si c'est une séquence
        if message.plugin_name.startswith('__sequence__'):
            if message.selected:
                # Charger la séquence
                seq_file = message.plugin_name.replace('__sequence__', '')
                sequence_path = Path('sequences') / seq_file
                self.load_sequence(sequence_path)
            return

        # Gestion normale des plugins
        if message.selected:
            # Vérifier si le plugin est multiple
            plugin_info = load_plugin_info(message.plugin_name)
            multiple = plugin_info.get('multiple', False)

            if not multiple and any(p[0] == message.plugin_name for p in self.selected_plugins):
                message.source.selected = False
                message.source.update_styles()
                return

            if message.plugin_name not in self.instance_counter:
                self.instance_counter[message.plugin_name] = 0
            self.instance_counter[message.plugin_name] += 1

            instance_id = self.instance_counter[message.plugin_name]
            self.selected_plugins.append((message.plugin_name, instance_id))
            logger.debug(f"Plugin ajouté: {message.plugin_name} (id: {instance_id})")
        else:
            self.selected_plugins = [(p, i) for p, i in self.selected_plugins if p != message.plugin_name]
            if message.plugin_name in self.instance_counter:
                del self.instance_counter[message.plugin_name]
            logger.debug(f"Plugin retiré: {message.plugin_name}")

        panel = self.query_one("#selected-plugins", SelectedPluginsPanel)
        panel.update_plugins(self.selected_plugins)

    def on_plugin_card_add_plugin_instance(self, message: PluginCard.AddPluginInstance) -> None:
        """Gérer l'ajout d'une instance pour les plugins multiples"""
        # Incrémenter le compteur d'instances
        if message.plugin_name not in self.instance_counter:
            self.instance_counter[message.plugin_name] = 0
        self.instance_counter[message.plugin_name] += 1

        # Ajouter la nouvelle instance à la liste
        instance_id = self.instance_counter[message.plugin_name]
        self.selected_plugins.append((message.plugin_name, instance_id))
        logger.debug(f"Added additional instance of plugin: {message.plugin_name} (id: {instance_id})")

        # Mettre à jour le panneau
        panel = self.query_one("#selected-plugins", SelectedPluginsPanel)
        panel.update_plugins(self.selected_plugins)

        # Effet visuel pour indiquer que l'instance a été ajoutée
        message.source.add_class("instance-added")

    async def action_configure_selected(self) -> None:
        """Configure selected plugins"""
        logger.debug("Starting action_configure_selected")

        try:
            from ui.config_screen.config_screen import PluginConfig

            if not self.selected_plugins:
                logger.debug("No plugins selected")
                self.notify("Aucun plugin sélectionné", severity="error")
                return

            logger.debug(f"Selected plugins: {self.selected_plugins}")

            # Créer l'écran de configuration pour tous les plugins sélectionnés
            logger.debug("Creating PluginConfig instance")
            sequence_file = str(self.sequence_file) if self.sequence_file else None
            logger.debug(f"Using sequence file: {sequence_file}")
            config_screen = PluginConfig(self.selected_plugins, sequence_file=sequence_file)

            # S'assurer que current_config existe et contient les configurations initiales
            if not hasattr(config_screen, 'current_config'):
                logger.debug("Adding default current_config attribute")
                config_screen.current_config = {}
                
            # Les configurations sont maintenant gérées par SequenceConfigManager
            logger.debug("Les configurations seront gérées par SequenceConfigManager")

            # Afficher l'écran de configuration et attendre qu'il se termine
            logger.debug("Pushing config screen")
            await self.push_screen(config_screen)
            logger.debug("Config screen pushed successfully")

            # Récupérer la configuration avec sécurité
            config = getattr(config_screen, 'current_config', None)
            logger.debug(f"Config returned: {config is not None}")

            # Si une configuration a été définie
            if config:
                # Mettre à jour les configurations des plugins sélectionnés
                updated_plugins = []
                for i, plugin_data in enumerate(self.selected_plugins):
                    plugin_name = plugin_data[0]
                    instance_id = plugin_data[1]
                    
                    # Récupérer la nouvelle config depuis l'ID unique
                    if i + 1 in config:  # +1 car on commence à 1 dans sequence_config_manager
                        new_config = config[i + 1]
                        # Créer un nouveau tuple avec la config mise à jour
                        updated_plugins.append((plugin_name, instance_id, new_config))
                        logger.debug(f"Config mise à jour pour {plugin_name} (ID: {instance_id}): {new_config}")
                    else:
                        # Garder l'ancienne config si elle existe
                        updated_plugins.append(plugin_data)
                        logger.debug(f"Pas de nouvelle config pour {plugin_name} (ID: {instance_id})")
                
                # Remplacer les plugins avec leurs nouvelles configs
                self.selected_plugins = updated_plugins
                
                # En mode auto-exécution, passer directement à l'écran d'exécution
                # Sauvegarder la séquence avec les nouvelles configs
                if self.sequence_file:
                    logger.debug(f"Sauvegarde de la séquence {self.sequence_file} avec les nouvelles configs")
                    self._save_sequence(self.sequence_file)
                
                if self.auto_execute:
                    logger.debug("Mode auto-exécution: passage direct à l'écran d'exécution")
                    logger.debug(f"Plugins configurés à exécuter: {self.selected_plugins}")
                    execution_screen = ExecutionScreen(self.selected_plugins)
                    await self.push_screen(execution_screen)
                    logger.debug("Execution screen pushed successfully")
                else:
                    logger.debug("Mode manuel: retour à l'écran de choix")
                    # Mettre à jour l'affichage des plugins sélectionnés
                    await self._update_selected_plugins_display()
            else:
                logger.debug("No configuration returned from config screen")

        except Exception as e:
            logger.error(f"Error in action_configure_selected: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.notify(f"Erreur: {str(e)}", severity="error")

    async def _update_selected_plugins_display(self) -> None:
        """Met à jour l'affichage des plugins sélectionnés avec leurs nouvelles configs"""
        try:
            # Récupérer le panel des plugins sélectionnés
            panel = self.query_one(SelectedPluginsPanel)
            if panel:
                # Mettre à jour l'affichage avec les nouvelles configs
                panel.update_plugins(self.selected_plugins)
                logger.debug("Affichage des plugins sélectionnés mis à jour")
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'affichage: {e}")
            logger.error(traceback.format_exc())
    
    def action_quit(self) -> None:
        """Quit the application"""
        logger.debug("Quitting application")
        self.exit()
