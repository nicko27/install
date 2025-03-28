import os
from ruamel.yaml import YAML
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
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
        yield Label("Plugins sélectionnés", classes="panel-title")  # Titre du panneau
        yield Container(id="selected-plugins-list")  # Conteneur pour la liste des plugins sélectionnés

    def update_plugins(self, plugins: list) -> None:
        """Update the display when selected plugins change"""
        self.selected_plugins = plugins  # Mettre à jour la liste des plugins sélectionnés
        container = self.query_one("#selected-plugins-list", Container)  # Rechercher le conteneur de la liste
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
                
                for j in range(idx + 1, len(items)):
                    # Si on rencontre une autre séquence, arrêter
                    if items[j].is_sequence:
                        break
                    
                    # Si ce plugin correspond à une entrée dans la séquence (nom et configuration)
                    current_plugin = {
                        'name': items[j].plugin_name,
                        'config': items[j].config if hasattr(items[j], 'config') else {}
                    }
                    
                    # Chercher une correspondance non utilisée dans la séquence
                    for seq_plugin in sequence_plugins:
                        # Vérifier le nom du plugin
                        if seq_plugin['name'] != current_plugin['name']:
                            continue
                            
                        # Vérifier que cette configuration n'a pas déjà été utilisée
                        if seq_plugin in plugins_found:
                            continue
                            
                        # Vérifier les configurations
                        seq_config = seq_plugin.get('config', {})
                        current_config = current_plugin.get('config', {})
                        
                        # Vérifier que toutes les clés de la séquence sont présentes avec les mêmes valeurs
                        config_match = True
                        for key, value in seq_config.items():
                            if key not in current_config or current_config[key] != value:
                                config_match = False
                                break
                                
                        if config_match:
                            # Marquer ce plugin comme faisant partie de la séquence
                            items[j].is_part_of_sequence = True
                            items[j].sequence_id = item.instance_id
                            plugins_found.append(seq_plugin)
                            logger.info(f"Plugin {items[j].plugin_name} marqué comme faisant partie de la séquence {item.instance_id}")
                            break
            
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
                    
                    for idx, (p, i) in enumerate(self.app.selected_plugins):
                        if i == instance_id and p.startswith('__sequence__'):
                            sequence_found = True
                            sequence_name = p
                            sequence_index = idx
                            break
                            
                    if not sequence_found:
                        # Si aucune séquence correspondante n'est trouvée, ne rien faire
                        logger.error(f"Séquence non trouvée pour l'ID: {instance_id}")
                        return
                    
                    # Identifier tous les plugins qui font partie de cette séquence
                    # Les plugins d'une séquence sont tous ceux qui suivent la séquence dans la liste
                    # jusqu'à la prochaine séquence ou la fin de la liste
                    plugins_to_remove = []
                    plugins_to_remove.append((sequence_name, instance_id))  # Ajouter la séquence elle-même
                    
                    # Parcourir les plugins après la séquence
                    for p, i in self.app.selected_plugins[sequence_index + 1:]:
                        # Si on trouve une autre séquence, on s'arrête
                        if p.startswith('__sequence__'):
                            break
                        # Sinon, on ajoute le plugin à la liste des plugins à supprimer
                        plugins_to_remove.append((p, i))
                    
                    # Supprimer tous les plugins identifiés
                    self.app.selected_plugins = [(p, i) for p, i in self.app.selected_plugins 
                                               if (p, i) not in plugins_to_remove]
                    
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
            self.app.selected_plugins = [(p, i) for p, i in self.app.selected_plugins if not (p == plugin_name and i == instance_id)]

            # Si c'était la dernière instance du plugin, on peut mettre à jour la carte
            if not any(p == plugin_name for p, _ in self.app.selected_plugins):
                for card in self.app.query(PluginCard):
                    if card.plugin_name == plugin_name:
                        card.selected = False
                        card.update_styles()
            
            # Mettre à jour l'affichage une seule fois à la fin
            self.update_plugins(self.app.selected_plugins)
