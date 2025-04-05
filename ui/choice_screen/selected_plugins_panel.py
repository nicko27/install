import os
from ruamel.yaml import YAML
from textual.app import ComposeResult
from textual.containers import Container, VerticalGroup
from textual.widgets import Label, Button, Static

from .plugin_list_item import PluginListItem
from .plugin_card import PluginCard
from ..utils.logging import get_logger

logger = get_logger('selected_plugins_panel')
yaml = YAML()

class SelectedPluginsPanel(Static):
    """Panel to display selected plugins and their order"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_plugins = []  # Liste des plugins sélectionnés
        self.sequence_map = {}  # Mapping des plugins appartenant à des séquences

    def compose(self) -> ComposeResult:
        with VerticalGroup(id="selected-plugins-list"):
            yield Label("Plugins sélectionnés", id="selected-plugins-list-title")  # Titre du panneau
            yield Container(id="selected-plugins-list-content")  # Conteneur pour la liste des plugins sélectionnés

    def update_plugins(self, plugins: list) -> None:
        """
        Met à jour l'affichage lorsque les plugins sélectionnés changent.
        
        Args:
            plugins: Liste des plugins sélectionnés
        """
        self.selected_plugins = plugins  # Mettre à jour la liste des plugins sélectionnés
        self._clear_content()  # Nettoyer le contenu actuel
        
        if not plugins:
            self._show_empty_message()
            return

        # Analyser les relations de séquence
        self._analyze_sequence_relationships(plugins)
        
        # Créer les éléments de la liste
        self._create_plugin_items(plugins)

    def _clear_content(self) -> None:
        """Efface le contenu du panneau"""
        container = self.query_one("#selected-plugins-list-content", Container)
        container.remove_children()

    def _show_empty_message(self) -> None:
        """Affiche un message quand aucun plugin n'est sélectionné"""
        container = self.query_one("#selected-plugins-list-content", Container)
        container.mount(Label("Aucun plugin sélectionné", classes="no-plugins"))

    def _analyze_sequence_relationships(self, plugins: list) -> None:
        """
        Analyse les relations de séquence entre les plugins.
        
        Args:
            plugins: Liste des plugins à analyser
        """
        # Réinitialiser le mapping
        self.sequence_map = {}
        
        # Identifier les séquences dans la liste
        sequence_indices = {}  # {sequence_id: index_dans_liste}
        for idx, plugin_data in enumerate(plugins):
            plugin_name = plugin_data[0]
            instance_id = plugin_data[1]
            
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
        
        # Pour chaque plugin, vérifier s'il appartient à une séquence
        for idx, plugin_data in enumerate(plugins):
            if idx in sequence_indices.values():
                continue  # Ignorer les séquences elles-mêmes
                
            plugin_name = plugin_data[0]
            if plugin_name.startswith('__sequence__'):
                continue
                
            # Extraire la configuration si disponible
            plugin_config = {}
            if len(plugin_data) >= 3:
                plugin_config = plugin_data[2]
                
            # Pour chaque séquence, vérifier si ce plugin fait partie de ses plugins
            for sequence_id, sequence_info in self.sequence_map.items():
                sequence_start_idx = sequence_info['start_index']
                
                # Un plugin fait partie d'une séquence s'il suit la séquence et correspond à un de ses plugins
                if idx > sequence_start_idx and self._plugin_matches_sequence(plugin_name, plugin_config, sequence_info['plugins']):
                    if 'member_indices' not in sequence_info:
                        sequence_info['member_indices'] = []
                    
                    sequence_info['member_indices'].append(idx)
                    logger.debug(f"Plugin {plugin_name} (index {idx}) identifié comme membre de la séquence {sequence_id}")
                    break

    def _load_sequence_details(self, sequence_name: str) -> dict:
        """
        Charge les détails d'une séquence à partir de son fichier YAML.
        
        Args:
            sequence_name: Nom de la séquence (format __sequence__nom)
            
        Returns:
            dict: Détails de la séquence ou dictionnaire vide si erreur
        """
        try:
            # Extraire le nom du fichier
            file_name = sequence_name.replace('__sequence__', '')
            if not file_name.endswith('.yml'):
                file_name = f"{file_name}.yml"
                
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            yaml_path = os.path.join(base_dir, 'sequences', file_name)
            
            if not os.path.exists(yaml_path):
                logger.warning(f"Fichier de séquence non trouvé: {yaml_path}")
                return {}
                
            with open(yaml_path, 'r', encoding='utf-8') as f:
                sequence_data = yaml.load(f)
                logger.debug(f"Séquence chargée: {yaml_path}")
                return sequence_data
                
        except Exception as e:
            logger.error(f"Erreur lors du chargement de la séquence {sequence_name}: {e}")
            return {}

    def _plugin_matches_sequence(self, plugin_name: str, plugin_config: dict, sequence_plugins: list) -> bool:
        """
        Vérifie si un plugin correspond à l'un des plugins définis dans une séquence.
        
        Args:
            plugin_name: Nom du plugin à vérifier
            plugin_config: Configuration du plugin
            sequence_plugins: Liste des plugins dans la séquence
            
        Returns:
            bool: True si le plugin correspond à un plugin de la séquence
        """
        for seq_plugin in sequence_plugins:
            # Vérifier si c'est le même plugin
            if isinstance(seq_plugin, dict) and 'name' in seq_plugin:
                seq_plugin_name = seq_plugin['name']
                
                if seq_plugin_name == plugin_name:
                    # Vérifier également les configurations si disponibles
                    if 'config' in seq_plugin and plugin_config:
                        seq_config = seq_plugin['config']
                        
                        # Une correspondance partielle suffit (le plugin peut avoir des configs supplémentaires)
                        match = True
                        for key, value in seq_config.items():
                            if key not in plugin_config or plugin_config[key] != value:
                                match = False
                                break
                                
                        if match:
                            return True
                    elif not seq_plugin.get('config') and not plugin_config:
                        # Les deux n'ont pas de config
                        return True
            elif isinstance(seq_plugin, str) and seq_plugin == plugin_name:
                # Format simple (juste le nom du plugin)
                return True
                
        return False

    def _create_plugin_items(self, plugins: list) -> None:
        """
        Crée et monte les éléments de liste pour les plugins sélectionnés.
        
        Args:
            plugins: Liste des plugins à afficher
        """
        container = self.query_one("#selected-plugins-list-content", Container)
        
        # Créer tous les éléments
        items = []
        for idx, plugin in enumerate(plugins, 1):
            # Vérifier si le plugin a une configuration
            if len(plugin) >= 3:
                plugin_name, instance_id, config = plugin
                item = PluginListItem((plugin_name, instance_id, config), idx)
            else:
                plugin_name, instance_id = plugin[:2]
                item = PluginListItem((plugin_name, instance_id), idx)
            
            items.append(item)
            
        # Marquer les éléments qui font partie de séquences
        for sequence_id, sequence_info in self.sequence_map.items():
            if 'member_indices' in sequence_info:
                # Trouver l'élément de la séquence elle-même
                sequence_item = items[sequence_info['start_index']]
                sequence_item.sequence_id = sequence_id
                
                # Marquer tous les membres de la séquence
                for member_idx in sequence_info['member_indices']:
                    member_item = items[member_idx]
                    member_item.set_sequence_attributes(
                        is_part_of_sequence=True,
                        sequence_id=sequence_id,
                        sequence_name=sequence_info['name']
                    )
                    
        # Monter tous les éléments
        for item in items:
            container.mount(item)

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
        
        if is_sequence_button:
            # Extraire l'ID de l'instance de séquence
            try:
                instance_id = int(button_id.replace('remove_seq_', ''))
                self._remove_sequence_and_members(instance_id)
            except (ValueError, IndexError) as e:
                logger.error(f"Erreur lors de l'extraction de l'ID de séquence: {e}")
        else:
            # Extraction standard pour les plugins
            try:
                parts = button_id.replace('remove_', '').split('_')
                instance_id = int(parts[-1])
                plugin_name = '_'.join(parts[:-1])
                self._remove_plugin(plugin_name, instance_id)
            except (ValueError, IndexError) as e:
                logger.error(f"Erreur lors de l'extraction de l'ID de plugin: {e}")

    def _remove_sequence_and_members(self, sequence_id: int) -> None:
        """
        Supprime une séquence et tous ses membres.
        
        Args:
            sequence_id: ID de l'instance de la séquence
        """
        indices_to_remove = []
        
        # Trouver la séquence
        sequence_found = False
        sequence_name = None
        
        for idx, plugin_data in enumerate(self.app.selected_plugins):
            plugin_name, instance_id = plugin_data[0], plugin_data[1]
            
            if instance_id == sequence_id and plugin_name.startswith('__sequence__'):
                sequence_found = True
                sequence_name = plugin_name
                indices_to_remove.append(idx)
                break
                
        if not sequence_found:
            logger.error(f"Séquence non trouvée pour l'ID: {sequence_id}")
            return
            
        # Trouver les membres de la séquence
        if sequence_id in self.sequence_map and 'member_indices' in self.sequence_map[sequence_id]:
            for member_idx in self.sequence_map[sequence_id]['member_indices']:
                indices_to_remove.append(member_idx)
                
        # Alternativement, trouver les plugins qui suivent jusqu'à la prochaine séquence
        else:
            start_idx = indices_to_remove[0] + 1
            while start_idx < len(self.app.selected_plugins):
                plugin_name = self.app.selected_plugins[start_idx][0]
                if plugin_name.startswith('__sequence__'):
                    break
                indices_to_remove.append(start_idx)
                start_idx += 1
                
        # Trier les indices en ordre décroissant pour supprimer de la fin vers le début
        indices_to_remove.sort(reverse=True)
        
        # Supprimer les plugins
        for idx in indices_to_remove:
            if 0 <= idx < len(self.app.selected_plugins):
                self.app.selected_plugins.pop(idx)
                
        # Mettre à jour l'affichage
        self.update_plugins(self.app.selected_plugins)
        
        # Mettre à jour les cartes de plugins
        if sequence_name:
            self._update_plugin_cards(sequence_name)

    def _remove_plugin(self, plugin_name: str, instance_id: int) -> None:
        """
        Supprime un plugin spécifique de la liste.
        
        Args:
            plugin_name: Nom du plugin à supprimer
            instance_id: ID de l'instance à supprimer
        """
        # Créer une nouvelle liste sans le plugin spécifié
        new_selected_plugins = [
            p for p in self.app.selected_plugins 
            if not (p[0] == plugin_name and p[1] == instance_id)
        ]
        
        # Mettre à jour la liste
        self.app.selected_plugins = new_selected_plugins
        
        # Mettre à jour l'affichage
        self.update_plugins(self.app.selected_plugins)
        
        # Vérifier si c'était la dernière instance de ce plugin
        if not any(p[0] == plugin_name for p in self.app.selected_plugins):
            self._update_plugin_cards(plugin_name)
            
    def _update_plugin_cards(self, plugin_name: str) -> None:
        """
        Met à jour l'état des cartes de plugins.
        
        Args:
            plugin_name: Nom du plugin dont les cartes doivent être mises à jour
        """
        for card in self.app.query(PluginCard):
            if card.plugin_name == plugin_name:
                card.selected = False
                card.update_styles()