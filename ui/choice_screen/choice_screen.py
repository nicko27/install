from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Label, Header, Footer, Button
import sys
import traceback
from typing import List, Dict, Any, Tuple, Optional, Set, Union

from ..utils.logging import get_logger
from ..execution_screen.execution_screen import ExecutionScreen

from .plugin_card import PluginCard
from .selected_plugins_panel import SelectedPluginsPanel
from .plugin_utils import load_plugin_info, get_plugin_folder_name
from .sequence_handler import SequenceHandler
from .template_handler import TemplateHandler

logger = get_logger('choice_screen')

class PluginInstance:
    """
    Représentation d'une instance de plugin.
    
    Cette classe remplace l'utilisation de tuples pour stocker les informations
    des plugins, offrant une structure plus claire et plus robuste.
    """
    
    def __init__(self, name: str, instance_id: int, config: Dict[str, Any] = None, metadata: Dict[str, Any] = None):
        """
        Initialise une instance de plugin.
        
        Args:
            name: Nom du plugin
            instance_id: ID unique de l'instance
            config: Configuration du plugin (par défaut: dictionnaire vide)
            metadata: Métadonnées supplémentaires (par défaut: dictionnaire vide)
        """
        self.name = name
        self.instance_id = instance_id
        self.config = config or {}
        self.metadata = metadata or {}
        
    @property
    def is_sequence(self) -> bool:
        """Indique si cette instance est une séquence."""
        return self.name.startswith('__sequence__')
        
    @property
    def from_sequence(self) -> bool:
        """Indique si cette instance provient d'une séquence."""
        return self.metadata.get('source') == 'sequence'
        
    @property
    def sequence_id(self) -> Optional[int]:
        """Retourne l'ID de la séquence parente, ou None."""
        return self.metadata.get('sequence_id')
        
    @property
    def unique_key(self) -> str:
        """Génère une clé unique pour cette instance."""
        return f"{self.name}_{self.instance_id}"
        
    def to_tuple(self) -> tuple:
        """Convertit l'instance en tuple pour compatibilité."""
        return (self.name, self.instance_id, self.config, self.metadata)
        
    @classmethod
    def from_tuple(cls, tuple_data):
        """Crée une instance à partir d'un tuple."""
        if len(tuple_data) == 2:
            return cls(tuple_data[0], tuple_data[1])
        elif len(tuple_data) == 3:
            return cls(tuple_data[0], tuple_data[1], tuple_data[2])
        elif len(tuple_data) >= 4:
            return cls(tuple_data[0], tuple_data[1], tuple_data[2], tuple_data[3])
        else:
            raise ValueError("Tuple de données invalide")

class Choice(App):
    """
    Application principale pour la sélection et la configuration des plugins.
    
    Cette classe gère l'interface de sélection des plugins et des séquences,
    ainsi que le passage à l'écran de configuration.
    """
    
    BINDINGS = [
        ("escape", "quit", "Quitter"),  # Raccourci pour quitter l'application
    ]

    CSS_PATH = "../styles/choice.tcss"  # Chemin vers le fichier CSS

    def __init__(self):
        """Initialise l'application de sélection des plugins."""
        super().__init__()
        logger.debug("Initialisation de l'application Choice")

        # Initialisation des gestionnaires
        self.sequence_handler = SequenceHandler()
        self.template_handler = TemplateHandler()
        self.report_manager = None  # Initialisé si besoin

        # État de l'application
        self.selected_plugins = []   # Liste d'objets PluginInstance
        self.next_instance_id = 0    # Compteur global pour les IDs d'instance
        self.plugin_templates = {}   # Templates par plugin
        self.sequence_file = None    # Fichier de séquence passé en argument
        self.auto_execute = False    # Mode exécution automatique
        self.report_file = None      # Fichier pour le rapport d'exécution
        self.report_format = 'csv'   # Format du rapport (csv ou txt)
        
        # Traiter les arguments de ligne de commande
        self._process_command_line_args()

    def _process_command_line_args(self) -> None:
        """
        Traite les arguments de ligne de commande.
        
        Format:
        - Le premier argument peut être un fichier de séquence
        - L'option --auto active l'exécution automatique
        - Les options --report=file.csv ou --format=txt définissent le rapport
        """
        if len(sys.argv) <= 1:
            return
            
        # Traiter le premier argument comme un fichier de séquence potentiel
        sequence_path = sys.argv[1]
        if not sequence_path.startswith('--'):
            sequence_file = Path(sequence_path)
            if sequence_file.exists():
                logger.info(f"Fichier de séquence détecté: {sequence_path}")
                self.sequence_file = sequence_file
                
        # Parcourir les autres arguments pour les options
        for arg in sys.argv[1:]:
            if arg == '--auto':
                self.auto_execute = True
                logger.info("Mode auto-exécution activé")
            elif arg.startswith('--report='):
                self.report_file = arg.split('=')[1]
                logger.info(f"Fichier de rapport défini: {self.report_file}")
            elif arg.startswith('--format='):
                self.report_format = arg.split('=')[1]
                logger.info(f"Format de rapport défini: {self.report_format}")

    def compose(self) -> ComposeResult:
        """
        Compose l'interface de sélection des plugins.
        
        Returns:
            ComposeResult: Résultat de la composition
        """
        yield Header()  # En-tête de l'application
        
        with Horizontal(id="main-content"):
            # Colonne gauche: cartes de plugins
            with Vertical(id="plugins-column"):
                yield Label("Sélectionnez vos plugins", classes="section-title")
                with ScrollableContainer(id="plugin-cards"):
                    yield from self._create_plugin_cards()
                    
            # Colonne droite: plugins sélectionnés
            yield SelectedPluginsPanel(id="selected-plugins")
            
        # Boutons d'action en bas
        with Horizontal(id="button-container"):
            yield Button("Configurer", id="configure_selected", variant="primary")
            
        yield Footer()

    def _create_plugin_cards(self) -> List[PluginCard]:
        """
        Crée les cartes de plugins et de séquences.
        
        Returns:
            List[PluginCard]: Liste des cartes de plugins créées
        """
        plugin_cards = []
        plugins_dir = Path('plugins')

        try:
            # 1. Récupérer les plugins valides
            valid_plugins = self._discover_valid_plugins(plugins_dir)
            
            # 2. Ajouter les séquences comme plugins spéciaux
            self._add_sequences_to_plugins(valid_plugins)
            
            # 3. Trier et créer les cartes
            valid_plugins.sort(key=lambda x: x[0].lower())
            for display_name, plugin_name in valid_plugins:
                plugin_cards.append(PluginCard(plugin_name))

            # 4. Si une séquence est spécifiée, la charger
            if self.sequence_file:
                self._load_sequence(self.sequence_file)
                
                # Si mode auto-exécution, passer directement à la configuration
                if self.auto_execute:
                    self.action_configure_selected()

            return plugin_cards
            
        except Exception as e:
            logger.error(f"Erreur lors de la découverte des plugins: {e}")
            logger.error(traceback.format_exc())
            return []

    def _discover_valid_plugins(self, plugins_dir: Path) -> List[Tuple[str, str]]:
        """
        Découvre les plugins valides dans le répertoire.
        
        Args:
            plugins_dir: Chemin vers le répertoire des plugins
            
        Returns:
            List[Tuple[str, str]]: Liste de tuples (nom_affichage, nom_plugin)
        """
        valid_plugins = []
        
        if not plugins_dir.exists():
            logger.error(f"Répertoire des plugins non trouvé: {plugins_dir}")
            return valid_plugins
            
        for plugin_path in plugins_dir.iterdir():
            if not plugin_path.is_dir():
                continue

            # Vérifier si c'est un plugin valide (settings.yml + exec.py/bash)
            settings_path = plugin_path / 'settings.yml'
            exec_py_path = plugin_path / 'exec.py'
            exec_bash_path = plugin_path / 'exec.bash'

            if (settings_path.exists() and (exec_py_path.exists() or exec_bash_path.exists())):
                try:
                    # Charger les infos du plugin
                    plugin_info = load_plugin_info(plugin_path.name)
                    display_name = plugin_info.get('name', plugin_path.name)
                    valid_plugins.append((display_name, plugin_path.name))

                    # Charger les templates du plugin
                    self.plugin_templates[plugin_path.name] = \
                        self.template_handler.get_plugin_templates(plugin_path.name)
                    logger.debug(f"Plugin valide trouvé: {plugin_path.name}, templates: {len(self.plugin_templates[plugin_path.name])}")
                except Exception as e:
                    logger.error(f"Erreur lors du chargement du plugin {plugin_path.name}: {e}")
        
        logger.info(f"Plugins valides trouvés: {len(valid_plugins)}")
        return valid_plugins

    def _add_sequences_to_plugins(self, valid_plugins: List[Tuple[str, str]]) -> None:
        """
        Ajoute les séquences disponibles à la liste des plugins.
        
        Args:
            valid_plugins: Liste des plugins valides à compléter
        """
        # Récupérer les séquences disponibles
        sequences = self.sequence_handler.get_available_sequences()
        logger.info(f"Séquences disponibles: {len(sequences)}")
        
        # Ajouter chaque séquence à la liste des plugins
        for seq in sequences:
            seq_name = seq['name']
            file_name = seq['file_name']
            # Ajouter directement la séquence sans préfixe dans le nom d'affichage
            valid_plugins.append((seq_name, f"__sequence__{file_name}"))
            logger.debug(f"Séquence ajoutée: {seq_name} ({file_name})")

    def _load_sequence(self, sequence_path: Path) -> None:
        """
        Charge une séquence depuis un fichier YAML.
        
        Args:
            sequence_path: Chemin vers le fichier de séquence
        """
        sequence = self.sequence_handler.load_sequence(sequence_path)
        if not sequence:
            logger.error(f"Impossible de charger la séquence: {sequence_path}")
            return

        try:
            # 1. Ajouter la séquence elle-même avec un ID unique
            sequence_id = self.next_instance_id
            self.next_instance_id += 1
            
            sequence_name = f"__sequence__{sequence_path.name}"
            sequence_instance = PluginInstance(
                name=sequence_name,
                instance_id=sequence_id,
                metadata={'source': 'file'}
            )
            
            self.selected_plugins.append(sequence_instance)
            logger.info(f"Séquence ajoutée: {sequence_name}, ID: {sequence_id}")

            # 2. Ajouter chaque plugin de la séquence
            for plugin_config in sequence['plugins']:
                self._add_sequence_plugin(plugin_config, sequence_id)
            
            # 3. Mettre à jour l'affichage
            self._update_selected_plugins_display()
            
            logger.info(f"Séquence chargée: {len(sequence['plugins'])} plugins")

        except Exception as e:
            logger.error(f"Erreur lors du chargement de la séquence: {e}")
            logger.error(traceback.format_exc())

    def _add_sequence_plugin(self, plugin_config: Dict[str, Any], sequence_id: int) -> None:
        """
        Ajoute un plugin de séquence à la liste des plugins sélectionnés.
        
        Args:
            plugin_config: Configuration du plugin dans la séquence
            sequence_id: Identifiant de la séquence parente
        """
        # Standardiser l'extraction du nom et de la configuration
        if isinstance(plugin_config, dict) and 'name' in plugin_config:
            plugin_name = plugin_config['name']
            
            # Toujours utiliser 'config' comme clé standard
            config = {}
            if 'config' in plugin_config:
                config = plugin_config['config']
            elif 'variables' in plugin_config:  # Migration des anciennes données
                config = plugin_config['variables']
                logger.warning(f"Ancienne clé 'variables' trouvée pour {plugin_name}, utilisation comme 'config'")
                
            # Appliquer un template si spécifié
            if 'template' in plugin_config:
                template_name = plugin_config['template']
                if template_name in self.plugin_templates.get(plugin_name, {}):
                    logger.debug(f"Application du template {template_name} pour {plugin_name}")
                    template_result = self.template_handler.apply_template(
                        plugin_name, template_name, plugin_config
                    )
                    if isinstance(template_result, dict) and 'config' in template_result:
                        config = template_result['config']
        elif isinstance(plugin_config, str):
            # Format simple: juste le nom du plugin
            plugin_name = plugin_config
            config = {}
        else:
            logger.error(f"Format de plugin invalide dans la séquence: {plugin_config}")
            return
        
        # Utiliser le compteur global et l'incrémenter
        instance_id = self.next_instance_id
        self.next_instance_id += 1
        
        # Créer et ajouter une nouvelle instance
        plugin_instance = PluginInstance(
            name=plugin_name,
            instance_id=instance_id,
            config=config,
            metadata={
                'source': 'sequence',
                'sequence_id': sequence_id
            }
        )
        
        self.selected_plugins.append(plugin_instance)
        logger.debug(f"Plugin ajouté depuis la séquence {sequence_id}: {plugin_name} (ID: {instance_id})")

    def _update_selected_plugins_display(self) -> None:
        """Met à jour l'affichage des plugins sélectionnés."""
        panel = self.query_one("#selected-plugins", SelectedPluginsPanel)
        
        # Convertir les instances en tuples pour compatibilité
        plugin_tuples = [plugin.to_tuple() for plugin in self.selected_plugins]
        
        panel.update_plugins(plugin_tuples)
        logger.debug("Affichage des plugins sélectionnés mis à jour")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Gère les clics sur les boutons de l'application.
        
        Args:
            event: Événement de bouton pressé
        """
        logger.debug(f"Bouton cliqué: {event.button.id}")
        
        if event.button.id == "configure_selected":
            await self.action_configure_selected()
        elif event.button.id == "quit":
            if self.auto_execute:
                # Sauvegarder le rapport avant de quitter
                self.save_execution_report()
            self.exit()

    def on_plugin_card_plugin_selection_changed(self, message: PluginCard.PluginSelectionChanged) -> None:
        """
        Gère les changements de sélection des plugins.
        
        Args:
            message: Message de changement de sélection
        """
        logger.debug(f"Changement sélection: {message.plugin_name} -> {message.selected}")

        # Vérifier si c'est une séquence
        if message.plugin_name.startswith('__sequence__'):
            if message.selected:
                # Charger la séquence
                seq_file = message.plugin_name.replace('__sequence__', '')
                sequence_path = Path('sequences') / seq_file
                self._load_sequence(sequence_path)
            else:
                # Trouver et supprimer la séquence et ses plugins
                for plugin in self.selected_plugins:
                    if plugin.name == message.plugin_name:
                        self._remove_sequence_and_members(plugin.instance_id)
                        break
            return

        # Gestion normale des plugins
        if message.selected:
            self._add_plugin(message.plugin_name, message.source)
        else:
            self._remove_plugin(message.plugin_name)

    def _add_plugin(self, plugin_name: str, source_card: PluginCard) -> None:
        """
        Ajoute un plugin à la liste des plugins sélectionnés.
        
        Args:
            plugin_name: Nom du plugin à ajouter
            source_card: Carte source de l'événement
        """
        # Vérifier si le plugin est multiple
        plugin_info = load_plugin_info(plugin_name)
        multiple = plugin_info.get('multiple', False)

        # Si non multiple, vérifier qu'il n'est pas déjà sélectionné
        if not multiple:
            manual_plugins = [p for p in self.selected_plugins 
                             if p.name == plugin_name and not p.from_sequence]
            
            if manual_plugins:
                source_card.selected = False
                source_card.update_styles()
                return

        # Utiliser le compteur global et l'incrémenter
        instance_id = self.next_instance_id
        self.next_instance_id += 1

        # Créer et ajouter une nouvelle instance
        plugin_instance = PluginInstance(
            name=plugin_name,
            instance_id=instance_id,
            metadata={'source': 'manual'}
        )
        
        self.selected_plugins.append(plugin_instance)
        logger.debug(f"Plugin ajouté manuellement: {plugin_name} (ID: {instance_id})")
        
        # Mettre à jour l'affichage
        self._update_selected_plugins_display()

    def _remove_plugin(self, plugin_name: str) -> None:
        """
        Retire un plugin manuel de la liste des plugins sélectionnés.
        
        Args:
            plugin_name: Nom du plugin à retirer
        """
        # Ne supprimer que les plugins ajoutés manuellement, pas ceux des séquences
        self.selected_plugins = [
            plugin for plugin in self.selected_plugins
            if plugin.name != plugin_name or plugin.from_sequence
        ]
        
        logger.debug(f"Plugin manuel retiré: {plugin_name}")
        
        # Mettre à jour l'affichage
        self._update_selected_plugins_display()

    def on_plugin_card_add_plugin_instance(self, message: PluginCard.AddPluginInstance) -> None:
        """
        Gère l'ajout d'une instance pour les plugins multiples.
        
        Args:
            message: Message d'ajout d'instance
        """
        # Utiliser le compteur global et l'incrémenter
        instance_id = self.next_instance_id
        self.next_instance_id += 1
        
        # Créer et ajouter une nouvelle instance
        plugin_instance = PluginInstance(
            name=message.plugin_name,
            instance_id=instance_id,
            metadata={'source': 'manual', 'multiple': True}
        )
        
        self.selected_plugins.append(plugin_instance)
        logger.debug(f"Instance supplémentaire ajoutée: {message.plugin_name} (ID: {instance_id})")

        # Mettre à jour l'affichage
        self._update_selected_plugins_display()

        # Effet visuel pour indiquer que l'instance a été ajoutée
        message.source.add_class("instance-added")

    def _remove_sequence_and_members(self, sequence_id: int) -> None:
        """
        Supprime une séquence et tous ses membres.
        
        Args:
            sequence_id: ID de l'instance de la séquence
        """
        # Filtrer la liste pour retirer la séquence et ses plugins
        self.selected_plugins = [
            plugin for plugin in self.selected_plugins
            if not (
                # Supprimer la séquence elle-même
                (plugin.is_sequence and plugin.instance_id == sequence_id) or 
                # Supprimer les plugins de cette séquence
                (plugin.from_sequence and plugin.sequence_id == sequence_id)
            )
        ]
        
        logger.debug(f"Séquence {sequence_id} et tous ses plugins retirés")
        
        # Mettre à jour l'affichage
        self._update_selected_plugins_display()

    async def action_configure_selected(self) -> None:
        """
        Passe à l'écran de configuration des plugins sélectionnés.
        """
        logger.debug("Début de la configuration des plugins sélectionnés")

        try:
            from ui.config_screen.config_screen import PluginConfig

            # Vérifier qu'il y a des plugins sélectionnés
            if not self.selected_plugins:
                logger.debug("Aucun plugin sélectionné")
                self.notify("Aucun plugin sélectionné", severity="error")
                return

            # Convertir les instances en tuples pour compatibilité
            plugin_tuples = [plugin.to_tuple() for plugin in self.selected_plugins]

            # Créer l'écran de configuration
            sequence_file = str(self.sequence_file) if self.sequence_file else None
            config_screen = PluginConfig(plugin_tuples, sequence_file=sequence_file)

            # Afficher l'écran de configuration
            await self.push_screen(config_screen)
            logger.debug("Écran de configuration affiché")

            # Récupérer la configuration après retour
            if hasattr(config_screen, 'current_config'):
                config = config_screen.current_config
                logger.debug(f"Configuration récupérée: {len(config)} plugins")
                
                # Mettre à jour les configurations des plugins
                self._update_plugins_config(config)
                
                # Sauvegarder la séquence si nécessaire
                if self.sequence_file:
                    logger.debug(f"Sauvegarde de la séquence: {self.sequence_file}")
                    self._save_sequence(self.sequence_file)
                
                # En mode auto-exécution, passer à l'exécution
                if self.auto_execute:
                    logger.debug("Mode auto-exécution: passage à l'exécution")
                    # Convertir les instances en tuples pour compatibilité
                    plugin_tuples = [plugin.to_tuple() for plugin in self.selected_plugins]
                    execution_screen = ExecutionScreen(plugin_tuples)
                    await self.push_screen(execution_screen)
            else:
                logger.debug("Pas de configuration retournée")

        except Exception as e:
            logger.error(f"Erreur lors de la configuration: {e}")
            logger.error(traceback.format_exc())
            self.notify(f"Erreur: {str(e)}", severity="error")

    def _update_plugins_config(self, config: Dict[str, Any]) -> None:
        """
        Met à jour les configurations des plugins sélectionnés.
        
        Args:
            config: Nouvelles configurations indexées par clé unique
        """
        # Mettre à jour chaque plugin
        for plugin in self.selected_plugins:
            plugin_key = plugin.unique_key
            
            # Si une nouvelle configuration existe pour ce plugin
            if plugin_key in config:
                # Mettre à jour la configuration
                plugin.config = config[plugin_key]
                logger.debug(f"Config mise à jour pour {plugin.name} (ID: {plugin.instance_id})")
            else:
                logger.debug(f"Pas de nouvelle config pour {plugin.name} (ID: {plugin.instance_id})")
        
        # Mettre à jour l'affichage
        self._update_selected_plugins_display()

    def _save_sequence(self, sequence_file: Path) -> bool:
        """
        Sauvegarde la liste des plugins sélectionnés dans un fichier de séquence.
        
        Args:
            sequence_file: Chemin du fichier de séquence
            
        Returns:
            bool: True si la sauvegarde a réussi
        """
        try:
            # Créer la structure de séquence
            sequence_data = {
                'name': sequence_file.stem,
                'description': f"Séquence générée automatiquement {sequence_file.name}",
                'plugins': []
            }
            
            # Ajouter chaque plugin (sauf les séquences)
            for plugin in self.selected_plugins:
                # Ignorer les séquences
                if plugin.is_sequence:
                    continue
                    
                # Format standardisé pour tous les plugins
                plugin_config = {
                    'name': plugin.name,
                    'config': plugin.config
                }
                
                sequence_data['plugins'].append(plugin_config)
                
            # Sauvegarder dans le fichier
            with open(sequence_file, 'w', encoding='utf-8') as f:
                self.sequence_handler.yaml.dump(sequence_data, f)
                
            logger.info(f"Séquence sauvegardée: {sequence_file}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de la séquence: {e}")
            logger.error(traceback.format_exc())
            return False

    def save_execution_report(self) -> None:
        """
        Sauvegarde le rapport d'exécution si configuré.
        """
        if not self.report_file:
            return
            
        try:
            # TODO: Implémentation du rapport d'exécution
            logger.info(f"Sauvegarde du rapport d'exécution: {self.report_file}")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du rapport: {e}")

    def action_quit(self) -> None:
        """Quitte l'application."""
        logger.debug("Quitter l'application")
        self.exit()