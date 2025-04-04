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

    def compose(self) -> ComposeResult:
        with VerticalGroup(id="selected-plugins-list"):
            yield Label("Plugins sélectionnés", id="selected-plugins-list-title")  # Titre du panneau
            yield Container(id="selected-plugins-list-content")  # Conteneur pour la liste des plugins sélectionnés

    def update_plugins(self, plugins: list) -> None:
        """Update the display when selected plugins change"""
        self.selected_plugins = plugins  # Mettre à jour la liste des plugins sélectionnés
        container = self.query_one("#selected-plugins-list-content", Container)  # Rechercher le conteneur de la liste
        container.remove_children()  # Retirer tous les enfants du conteneur

        if not plugins:
            container.mount(Label("Aucun plugin sélectionné", classes="no-plugins"))  # Afficher un message si aucun plugin n'est sélectionné
            return

        # Créer tous les éléments de la liste
        items = []
        for idx, plugin in enumerate(plugins, 1):
            # Vérifier si le plugin a une configuration
            if isinstance(plugin, tuple) and len(plugin) >= 2:
                plugin_name, instance_id = plugin[:2]
                # Chercher la configuration dans l'app
                config = {}
                plugin_instance_id = f"{plugin_name}_{instance_id}"
                if hasattr(self.app, 'current_config') and plugin_instance_id in self.app.current_config:
                    config = self.app.current_config[plugin_instance_id]
                    logger.info(f"Configuration trouvée pour {plugin_instance_id}: {config}")
                # Créer le plugin avec sa configuration
                item = PluginListItem((plugin_name, instance_id, config), idx)
            else:
                # Fallback pour les anciens formats
                item = PluginListItem(plugin, idx)
            items.append(item)
            
        # Approche simplifiée pour la gestion des séquences
        # 1. Identifier les séquences dans la liste
        # 2. Pour chaque séquence, marquer tous les plugins qui en font partie
        
        # Parcourir la liste pour identifier et marquer les séquences
        for idx, item in enumerate(items):
            # Vérifier si cet élément est une séquence
            if item.is_sequence:
                # Marquer la séquence elle-même
                item.sequence_id = item.instance_id
                logger.info(f"Séquence détectée: {item.plugin_name}, id: {item.instance_id}")
                
                # Extraire le nom du fichier YAML
                sequence_name = item.plugin_name.replace('__sequence__', '')
                if not sequence_name.endswith('.yml'):
                    sequence_name = f"{sequence_name}.yml"
                
                # Charger le fichier YAML pour obtenir la liste des plugins
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                yaml_path = os.path.join(base_dir, 'sequences', sequence_name)
                
                # Liste des plugins dans la séquence avec leur configuration
                sequence_plugins = []
                
                if os.path.exists(yaml_path):
                    try:
                        with open(yaml_path, 'r', encoding='utf-8') as f:
                            sequence_data = yaml.load(f)
                        
                        if 'plugins' in sequence_data and isinstance(sequence_data['plugins'], list):
                            # Extraire les plugins et leurs configurations
                            for plugin_entry in sequence_data['plugins']:
                                if isinstance(plugin_entry, dict) and 'name' in plugin_entry:
                                    # Créer un identifiant unique basé sur le nom et la configuration
                                    plugin_id = {
                                        'name': plugin_entry['name'],
                                        'config': plugin_entry.get('config', {})
                                    }
                                    sequence_plugins.append(plugin_id)
                                elif isinstance(plugin_entry, str):
                                    # Pour les plugins sans configuration
                                    plugin_id = {
                                        'name': plugin_entry,
                                        'config': {}
                                    }
                                    sequence_plugins.append(plugin_id)
                            
                            logger.info(f"Plugins dans la séquence {sequence_name}: {sequence_plugins}")
                    except Exception as e:
                        logger.error(f"Erreur lors du chargement de la séquence {sequence_name}: {e}")
                else:
                    logger.warning(f"Fichier de séquence non trouvé: {yaml_path}")
                
                # Marquer tous les plugins suivants qui font partie de la séquence
                # jusqu'à la prochaine séquence ou jusqu'à ce qu'on ait trouvé tous les plugins de la séquence
                plugins_found = []
                
                logger.debug(f"Recherche des plugins pour la séquence {sequence_name} avec ID {item.instance_id}")
                logger.debug(f"Nombre de plugins attendus dans la séquence: {len(sequence_plugins)}")
                
                # Générer des identifiants uniques pour chaque plugin de la séquence basés sur le nom ET la configuration
                # Cela permet de différencier les instances multiples du même plugin avec des configurations différentes
                sequence_plugin_identifiers = []
                for seq_plugin in sequence_plugins:
                    # Créer un identifiant unique basé sur le nom et les valeurs de configuration
                    config_str = ""
                    for key, value in sorted(seq_plugin.get('config', {}).items()):
                        config_str += f"{key}:{value};"
                    unique_id = f"{seq_plugin['name']}_{config_str}"
                    sequence_plugin_identifiers.append({
                        'id': unique_id,
                        'plugin': seq_plugin,
                        'used': False  # Pour suivre si ce plugin a déjà été utilisé
                    })
                
                logger.debug(f"Identifiants uniques générés pour les plugins de la séquence: {[p['id'] for p in sequence_plugin_identifiers]}")
                
                # Parcourir tous les plugins pour trouver ceux qui font partie de la séquence
                # Ne pas se limiter aux plugins qui suivent immédiatement la séquence
                for j in range(0, len(items)):
                    # Ignorer les séquences et le plugin de séquence actuel
                    if items[j].is_sequence or j == idx:
                        continue
                    
                    # Si ce plugin correspond à une entrée dans la séquence (nom et configuration)
                    current_plugin = {
                        'name': items[j].plugin_name,
                        'config': items[j].config if hasattr(items[j], 'config') else {}
                    }
                    
                    # Générer l'identifiant unique pour ce plugin
                    config_str = ""
                    for key, value in sorted(current_plugin.get('config', {}).items()):
                        config_str += f"{key}:{value};"
                    current_id = f"{current_plugin['name']}_{config_str}"
                    
                    logger.debug(f"Vérification du plugin {current_plugin['name']} à l'index {j} avec ID: {current_id}")
                    
                    # Chercher une correspondance non utilisée dans la séquence en utilisant les identifiants uniques
                    match_found = False
                    
                    # Parcourir les identifiants uniques des plugins de la séquence
                    for seq_identifier in sequence_plugin_identifiers:
                        # Si cet identifiant a déjà été utilisé, passer au suivant
                        if seq_identifier['used']:
                            continue
                            
                        # Vérifier si le nom du plugin correspond
                        seq_plugin = seq_identifier['plugin']
                        if seq_plugin['name'] != current_plugin['name']:
                            logger.debug(f"Nom de plugin différent: {seq_plugin['name']} != {current_plugin['name']}")
                            continue
                            
                        # Vérifier les configurations
                        seq_config = seq_plugin.get('config', {})
                        current_config = current_plugin.get('config', {})
                        
                        logger.debug(f"Comparaison des configurations - Séquence: {seq_config}, Actuel: {current_config}")
                        
                        # Vérifier que toutes les clés de la séquence sont présentes avec les mêmes valeurs
                        config_match = True
                        for key, value in seq_config.items():
                            if key not in current_config or current_config[key] != value:
                                logger.debug(f"Non-correspondance de configuration pour la clé {key}: {value} != {current_config.get(key, 'non défini')}")
                                config_match = False
                                break
                                
                        if config_match:
                            # Marquer ce plugin comme faisant partie de la séquence en utilisant la méthode dédiée
                            # qui va aussi rafraîchir l'affichage
                            items[j].set_sequence_attributes(
                                is_part_of_sequence=True,
                                sequence_id=item.instance_id,
                                sequence_name=sequence_name.replace('.yml', '')
                            )
                            
                            # Marquer cet identifiant comme utilisé
                            seq_identifier['used'] = True
                            
                            # Copier la configuration du plugin de la séquence dans le plugin actuel
                            # pour s'assurer qu'il a la bonne configuration
                            if hasattr(items[j], 'config') and seq_config:
                                items[j].config.update(seq_config)
                                logger.debug(f"Configuration mise à jour pour {items[j].plugin_name}: {items[j].config}")
                            
                            match_found = True
                            logger.warning(f"Plugin {items[j].plugin_name} marqué comme faisant partie de la séquence {item.instance_id} (nom: {sequence_name})")
                            break
                    
                    if not match_found:
                        logger.debug(f"Aucune correspondance trouvée pour le plugin {current_plugin['name']} dans la séquence")
            
        # Monter tous les éléments
        for item in items:
            container.mount(item)  # Ajouter l'élément au conteneur


    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses in the selected plugins panel"""
        if event.button.id and event.button.id.startswith('remove_'):
            # Vérifier si c'est un bouton de séquence
            is_sequence_button = 'sequence-remove-button' in event.button.classes
            
            if is_sequence_button:
                # Pour les séquences, extraire l'ID de l'instance directement
                # Format: remove_seq_X où X est l'instance_id
                try:
                    instance_id = int(event.button.id.replace('remove_seq_', ''))
                    # Trouver la séquence correspondante dans la liste
                    sequence_found = False
                    sequence_name = None
                    sequence_index = None
                    
                    for idx, plugin_data in enumerate(self.app.selected_plugins):
                        # Extraire le nom du plugin et l'ID de l'instance
                        if len(plugin_data) >= 2:
                            p_name = plugin_data[0]
                            p_instance = plugin_data[1]
                            
                            if p_instance == instance_id and p_name.startswith('__sequence__'):
                                sequence_found = True
                                sequence_name = p_name
                                sequence_index = idx
                                break
                            
                    if not sequence_found:
                        # Si aucune séquence correspondante n'est trouvée, ne rien faire
                        logger.error(f"Séquence non trouvée pour l'ID: {instance_id}")
                        return
                    
                    # Identifier tous les plugins qui font partie de cette séquence
                    # Les plugins d'une séquence sont tous ceux qui suivent la séquence dans la liste
                    # jusqu'à la prochaine séquence ou la fin de la liste
                    indices_to_remove = [sequence_index]  # Commencer par l'indice de la séquence
                    
                    # Parcourir les plugins après la séquence pour trouver ceux à supprimer
                    current_index = sequence_index + 1
                    while current_index < len(self.app.selected_plugins):
                        plugin_data = self.app.selected_plugins[current_index]
                        plugin_name = plugin_data[0]
                        
                        # Si on trouve une autre séquence, on s'arrête
                        if plugin_name.startswith('__sequence__'):
                            break
                            
                        # Sinon, on ajoute l'indice à la liste des indices à supprimer
                        indices_to_remove.append(current_index)
                        current_index += 1
                    
                    # Supprimer tous les plugins identifiés en créant une nouvelle liste
                    # sans les éléments aux indices à supprimer
                    new_selected_plugins = []
                    for idx, plugin_data in enumerate(self.app.selected_plugins):
                        if idx not in indices_to_remove:
                            new_selected_plugins.append(plugin_data)
                    
                    self.app.selected_plugins = new_selected_plugins
                    
                    # Définir plugin_name pour la mise à jour des cartes plus bas
                    plugin_name = sequence_name
                    
                except (ValueError, IndexError):
                    # En cas d'erreur, ne rien faire
                    logger.error(f"Impossible de parser l'ID du bouton: {event.button.id}")
                    return
            else:
                # Pour les plugins normaux
                # Format: remove_name_X où X est l'instance_id
                parts = event.button.id.replace('remove_', '').split('_')
                try:
                    instance_id = int(parts[-1])
                    # Le nom du plugin est tout ce qui est entre 'remove_' et le dernier _
                    plugin_name = '_'.join(parts[:-1])
                except (ValueError, IndexError):
                    # En cas d'erreur, ne rien faire
                    logger.error(f"Impossible de parser l'ID du bouton: {event.button.id}")
                    return
            
            # Retirer l'instance spécifique de la liste
            # Pour les séquences comme pour les plugins normaux, on ne supprime que l'entrée spécifique
            # Utiliser une approche qui fonctionne avec des tuples de différentes longueurs
            new_selected_plugins = []
            for plugin_data in self.app.selected_plugins:
                # Extraire le nom du plugin et l'ID de l'instance
                p_name = plugin_data[0]
                p_instance = plugin_data[1]
                # Ne garder que les plugins qui ne correspondent pas au plugin à supprimer
                if not (p_name == plugin_name and p_instance == instance_id):
                    new_selected_plugins.append(plugin_data)
            self.app.selected_plugins = new_selected_plugins

            # Si c'était la dernière instance du plugin, on peut mettre à jour la carte
            if not any(plugin_data[0] == plugin_name for plugin_data in self.app.selected_plugins):
                for card in self.app.query(PluginCard):
                    if card.plugin_name == plugin_name:
                        card.selected = False
                        card.update_styles()
            
            # Mettre à jour l'affichage une seule fois à la fin
            self.update_plugins(self.app.selected_plugins)
