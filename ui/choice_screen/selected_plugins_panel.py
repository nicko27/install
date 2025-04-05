from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List, Union
from textual.app import ComposeResult
from textual.containers import Container, VerticalGroup
from textual.widgets import Label, Button, Static
from textual.css.query import NoMatches

from .plugin_list_item import PluginListItem
from .plugin_card import PluginCard
from .sequence_handler import SequenceHandler
from ..utils.logging import get_logger

logger = get_logger('selected_plugins_panel')

class SelectedPluginsPanel(Static):
    """
    Panneau affichant les plugins sélectionnés et leur ordre.
    
    Cette classe gère l'affichage des plugins sélectionnés, leur organisation
    en séquences, et les actions associées (suppression).
    """
    
    def __init__(self, *args, **kwargs):
        """
        Initialise le panneau des plugins sélectionnés.
        
        Args:
            *args: Arguments positionnels pour la classe parente
            **kwargs: Arguments nommés pour la classe parente
        """
        super().__init__(*args, **kwargs)
        self.selected_plugins = []  # Liste des plugins sélectionnés (tuples)
        self.sequence_map = {}      # Mapping des plugins appartenant à des séquences
        self.sequence_handler = SequenceHandler()  # Gestionnaire de séquences

    def compose(self) -> ComposeResult:
        """
        Compose l'interface du panneau.
        
        Returns:
            ComposeResult: Résultat de la composition
        """
        with VerticalGroup(id="selected-plugins-list"):
            yield Label("Plugins sélectionnés", id="selected-plugins-list-title")
            yield Container(id="selected-plugins-list-content")

    def update_plugins(self, plugins: List) -> None:
        """
        Met à jour l'affichage lorsque les plugins sélectionnés changent.
        
        Args:
            plugins: Liste des plugins sélectionnés (tuples)
        """
        self.selected_plugins = plugins
        self._clear_content()
        
        if not plugins:
            self._show_empty_message()
            return

        # Analyser les relations de séquence
        self._analyze_sequence_relationships(plugins)
        
        # Créer les éléments de la liste
        self._create_plugin_items(plugins)
        
        logger.debug(f"Panneau mis à jour avec {len(plugins)} plugins")

    def _clear_content(self) -> None:
        """Efface le contenu du panneau."""
        try:
            container = self.query_one("#selected-plugins-list-content", Container)
            container.remove_children()
        except NoMatches:
            logger.error("Container #selected-plugins-list-content non trouvé")

    def _show_empty_message(self) -> None:
        """Affiche un message quand aucun plugin n'est sélectionné."""
        try:
            container = self.query_one("#selected-plugins-list-content", Container)
            container.mount(Label("Aucun plugin sélectionné", classes="no-plugins"))
        except NoMatches:
            logger.error("Container #selected-plugins-list-content non trouvé")

    def _analyze_sequence_relationships(self, plugins: List) -> None:
        """
        Analyse les relations de séquence entre les plugins.
        
        Cette méthode identifie quels plugins font partie de quelles séquences
        et construit une carte des relations.
        
        Args:
            plugins: Liste des plugins à analyser (tuples)
        """
        # Réinitialiser le mapping
        self.sequence_map = {}
        
        # Identifier les séquences dans la liste
        sequence_indices = {}  # {sequence_id: index_dans_liste}
        for idx, plugin_data in enumerate(plugins):
            plugin_name = plugin_data[0]
            instance_id = plugin_data[1]
            
            if not isinstance(plugin_name, str):
                logger.warning(f"Type de nom de plugin inattendu à l'index {idx}: {type(plugin_name)}")
                continue
                
            if plugin_name.startswith('__sequence__'):
                sequence_indices[instance_id] = idx
                logger.debug(f"Séquence détectée: {plugin_name}, ID: {instance_id}, index: {idx}")
                
                # Charger les détails de la séquence
                sequence_details = self._load_sequence_details(plugin_name)
                if sequence_details and 'plugins' in sequence_details:
                    self.sequence_map[instance_id] = {
                        'name': sequence_details.get('name', plugin_name.replace('__sequence__', '')),
                        'plugins': sequence_details.get('plugins', []),
                        'start_index': idx
                    }
        
        # Pour chaque plugin, vérifier s'il appartient à une séquence en utilisant les métadonnées
        for idx, plugin_data in enumerate(plugins):
            # Ignorer les séquences elles-mêmes
            if idx in sequence_indices.values():
                continue
                
            # Vérifier si le plugin a des métadonnées
            metadata = {}
            if len(plugin_data) >= 4:
                metadata = plugin_data[3]
                
            # Vérifier si le plugin fait partie d'une séquence
            if isinstance(metadata, dict) and metadata.get('source') == 'sequence':
                sequence_id = metadata.get('sequence_id')
                if sequence_id in self.sequence_map:
                    if 'member_indices' not in self.sequence_map[sequence_id]:
                        self.sequence_map[sequence_id]['member_indices'] = []
                    
                    self.sequence_map[sequence_id]['member_indices'].append(idx)
                    logger.debug(f"Plugin {plugin_data[0]} (index {idx}) identifié comme membre de la séquence {sequence_id}")

    def _load_sequence_details(self, sequence_name: str) -> Dict[str, Any]:
        """
        Charge les détails d'une séquence à partir de son fichier YAML.
        
        Args:
            sequence_name: Nom de la séquence (format __sequence__nom)
            
        Returns:
            Dict[str, Any]: Détails de la séquence ou dictionnaire vide si erreur
        """
        try:
            # Extraire le nom du fichier
            file_name = sequence_name.replace('__sequence__', '')
            if not file_name.endswith('.yml'):
                file_name = f"{file_name}.yml"
                
            sequence_path = Path('sequences') / file_name
            return self.sequence_handler.load_sequence(sequence_path) or {}
                
        except Exception as e:
            logger.error(f"Erreur lors du chargement de la séquence {sequence_name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}

    def _create_plugin_items(self, plugins: List) -> None:
        """
        Crée et monte les éléments de liste pour les plugins sélectionnés.
        
        Args:
            plugins: Liste des plugins à afficher (tuples)
        """
        try:
            container = self.query_one("#selected-plugins-list-content", Container)
        except NoMatches:
            logger.error("Container #selected-plugins-list-content non trouvé")
            return
            
        # Créer tous les éléments
        items = []
        for idx, plugin_tuple in enumerate(plugins, 1):
            item = None
            
            try:
                # Créer l'élément pour ce plugin
                item = PluginListItem(plugin_tuple, idx)
                items.append(item)
            except Exception as e:
                logger.error(f"Erreur lors de la création de l'élément {idx}: {e}")
                import traceback
                logger.error(traceback.format_exc())
            
        # Marquer les éléments qui font partie de séquences
        for sequence_id, sequence_info in self.sequence_map.items():
            if 'member_indices' in sequence_info:
                try:
                    # Trouver l'élément de la séquence elle-même
                    sequence_item = items[sequence_info['start_index']]
                    sequence_item.sequence_id = sequence_id
                    
                    # Marquer tous les membres de la séquence
                    for member_idx in sequence_info['member_indices']:
                        if 0 <= member_idx < len(items):
                            member_item = items[member_idx]
                            member_item.set_sequence_attributes(
                                is_part_of_sequence=True,
                                sequence_id=sequence_id,
                                sequence_name=sequence_info['name']
                            )
                except IndexError:
                    logger.error(f"Index hors limites lors du marquage des membres de séquence: {sequence_id}")
                except Exception as e:
                    logger.error(f"Erreur lors du marquage des membres de séquence {sequence_id}: {e}")
                    
        # Monter tous les éléments
        for item in items:
            try:
                container.mount(item)
            except Exception as e:
                logger.error(f"Erreur lors du montage de l'élément: {e}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Gère les clics sur les boutons dans le panneau.
        
        Args:
            event: Événement de bouton pressé
        """
        if not event.button.id or not event.button.id.startswith('remove_'):
            return
            
        button_id = event.button.id
        is_sequence_button = 'sequence-remove-button' in event.button.classes
        
        try:
            if is_sequence_button:
                # Extraire l'ID de l'instance de séquence
                instance_id = int(button_id.replace('remove_seq_', ''))
                await self._remove_sequence_and_members(instance_id)
            else:
                # Extraction standard pour les plugins
                parts = button_id.replace('remove_', '').split('_')
                instance_id = int(parts[-1])
                plugin_name = '_'.join(parts[:-1])
                await self._remove_plugin(plugin_name, instance_id)
        except (ValueError, IndexError) as e:
            logger.error(f"Erreur lors de l'extraction de l'ID: {e} pour bouton {button_id}")
        except Exception as e:
            logger.error(f"Erreur inattendue lors du traitement du bouton {button_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _remove_sequence_and_members(self, sequence_id: int) -> None:
        """
        Supprime une séquence et tous ses membres.
        
        Args:
            sequence_id: ID de l'instance de la séquence
        """
        # Trouver tous les plugins à supprimer
        sequence_found = False
        sequence_name = None
        plugins_to_remove = []
        
        # 1. Trouver la séquence elle-même
        for plugin in self.app.selected_plugins:
            plugin_name = plugin[0] if isinstance(plugin, tuple) else plugin.name
            instance_id = plugin[1] if isinstance(plugin, tuple) else plugin.instance_id
            
            # Si c'est la séquence
            if instance_id == sequence_id and plugin_name.startswith('__sequence__'):
                sequence_found = True
                sequence_name = plugin_name
                break
        
        if not sequence_found:
            logger.error(f"Séquence non trouvée pour l'ID: {sequence_id}")
            return
        
        # 2. Appeler la méthode de l'application pour supprimer la séquence et ses membres
        if hasattr(self.app, '_remove_sequence_and_members'):
            await self.app._remove_sequence_and_members(sequence_id)
        else:
            logger.error("La méthode _remove_sequence_and_members n'existe pas dans l'application")

    async def _remove_plugin(self, plugin_name: str, instance_id: int) -> None:
        """
        Supprime un plugin spécifique de la liste.
        
        Args:
            plugin_name: Nom du plugin à supprimer
            instance_id: ID de l'instance à supprimer
        """
        # Appeler la méthode de l'application pour supprimer le plugin
        if hasattr(self.app, '_remove_plugin'):
            await self.app._remove_plugin(plugin_name)
        else:
            logger.error("La méthode _remove_plugin n'existe pas dans l'application")
            
    async def _update_plugin_cards(self, plugin_name: str) -> None:
        """
        Met à jour l'état des cartes de plugins.
        
        Args:
            plugin_name: Nom du plugin dont les cartes doivent être mises à jour
        """
        try:
            # Rechercher toutes les cartes correspondant au plugin
            for card in self.app.query(PluginCard):
                if card.plugin_name == plugin_name:
                    card.selected = False
                    card.update_styles()
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour des cartes pour {plugin_name}: {e}")
            import traceback
            logger.error(traceback.format_exc())