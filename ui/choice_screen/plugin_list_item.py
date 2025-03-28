import os
from ruamel.yaml import YAML
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Label, Button

from .plugin_utils import load_plugin_info
from ..utils.logging import get_logger

logger = get_logger('plugin_list_item')
yaml = YAML()

class PluginListItem(Horizontal):
    """Représente un élément dans la liste des plugins sélectionnés"""

    def load_sequence_info(self, sequence_name):
        """Charge les informations d'une séquence depuis son fichier YAML"""
        # Extraire le nom du fichier de séquence (sans le préfixe __sequence__)
        file_name = sequence_name.replace('__sequence__', '')
        logger.debug(f"Chargement de la séquence: {sequence_name}, nom de fichier: {file_name}")
        
        if not file_name:
            logger.warning("Nom de fichier vide pour la séquence")
            return {"name": "Sans nom", "icon": "⚙️ "}
            
        # Chercher le fichier YAML correspondant dans le dossier sequences
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        # S'assurer que le nom du fichier a l'extension .yml si ce n'est pas déjà le cas
        if not file_name.endswith('.yml'):
            file_name = f"{file_name}.yml"
        yaml_path = os.path.join(base_dir, 'sequences', file_name)
        logger.debug(f"Chemin du fichier YAML: {yaml_path}, existe: {os.path.exists(yaml_path)}")
        
        if not os.path.exists(yaml_path):
            logger.warning(f"Fichier de séquence non trouvé: {yaml_path}")
            return {"name": file_name, "icon": "⚙️ "}
            
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                sequence_data = yaml.load(f)
                logger.debug(f"Informations de séquence chargées: {sequence_data}")
                
                # Vérifier si le fichier YAML contient un nom
                if sequence_data and 'name' in sequence_data:
                    sequence_name = sequence_data['name']
                    logger.info(f"Nom de séquence trouvé dans le YAML: {sequence_name}")
                    return {"name": sequence_name, "icon": "⚙️ "}
                else:
                    logger.warning(f"Pas de nom dans le fichier YAML, utilisation du nom de fichier: {file_name}")
                    return {"name": file_name, "icon": "⚙️ "}
        except Exception as e:
            logger.error(f"Erreur lors du chargement de la séquence {file_name}: {e}")
            return {"name": file_name, "icon": "⚙️ "}
    
    def __init__(self, plugin_data: tuple, index: int):
        super().__init__()
        # Gérer le cas où plugin_data est un tuple de 3 éléments (nom, id, config)
        if len(plugin_data) == 3:
            self.plugin_name, self.instance_id, self.config = plugin_data
            logger.info(f"Plugin avec config: {self.plugin_name}, config: {self.config}")
        else:
            self.plugin_name, self.instance_id = plugin_data
            self.config = {}
            logger.info(f"Plugin sans config: {self.plugin_name}")
            
        self.index = index  # Index de l'élément dans la liste
        self.is_sequence = self.plugin_name.startswith('__sequence__')
        logger.warning(f"Initialisation de PluginListItem: {self.plugin_name}, is_sequence: {self.is_sequence}, type: {type(self.plugin_name)}, startswith: {self.plugin_name.startswith('__sequence__') if isinstance(self.plugin_name, str) else 'N/A'}")
        
        # Déterminer si ce plugin fait partie d'une séquence
        # Un plugin fait partie d'une séquence s'il est précédé par une séquence et qu'il n'y a pas d'autre séquence entre les deux
        self.is_part_of_sequence = False
        self.sequence_id = None
        
        # Cette vérification sera faite dans la méthode update_sequence_info
        
        # Définir une valeur par défaut différente pour les séquences
        if self.is_sequence:
            # Pour les séquences, charger les informations depuis le fichier YAML
            default_info = self.load_sequence_info(self.plugin_name)
            logger.warning(f"Informations de séquence chargées pour {self.plugin_name}: {default_info}")
        else:
            default_info = {
                "name": self.plugin_name,
                "icon": "📦"
            }
        
        self.plugin_info = load_plugin_info(self.plugin_name, default_info)
        logger.warning(f"Plugin info final pour {self.plugin_name}: {self.plugin_info}")

    def update_sequence_info(self, all_plugins: list) -> None:
        """
        Cette méthode est maintenant gérée par SelectedPluginsPanel.
        Conservée pour compatibilité mais ne fait plus rien.
        
        Args:
            all_plugins: Liste de tous les plugins sélectionnés (tuples de (nom, instance_id))
        """
        # Cette méthode est conservée pour compatibilité, mais la logique est maintenant dans SelectedPluginsPanel
        # pour assurer une gestion cohérente des séquences et éviter les problèmes de style
        pass
    
    def compose(self) -> ComposeResult:
        # Pour les séquences, s'assurer que nous utilisons le nom du YAML
        # Sauvegarder l'état original de is_sequence pour l'utiliser plus tard
        original_is_sequence = self.is_sequence
        
        if original_is_sequence:
            # Récupérer les informations de séquence à nouveau pour s'assurer qu'elles sont à jour
            seq_info = self.load_sequence_info(self.plugin_name)
            name = seq_info.get('name', self.plugin_name.replace('__sequence__', ''))
            icon = seq_info.get('icon', '⚙️')
            logger.info(f"Séquence: {self.plugin_name}, nom chargé: {name}")
        else:
            # Pour les plugins normaux
            name = self.plugin_info.get('name', self.plugin_name)  # Nom du plugin
            icon = self.plugin_info.get('icon', '📦')  # Icône du plugin
        
        logger.info(f"Composition de l'élément {self.plugin_name}, nom: {name}, is_sequence: {original_is_sequence}")
        
        # Déterminer les classes du label
        if original_is_sequence:
            # Si c'est une séquence, utiliser le style de séquence
            label_classes = "plugin-list-name sequence-list-name"
        elif self.is_part_of_sequence and self.sequence_id is not None:
            # Si c'est un plugin faisant partie d'une séquence active, utiliser le style de plugin de séquence
            label_classes = f"plugin-list-name sequence-item-name sequence-plugin sequence-{self.sequence_id}"
        else:
            # Sinon, utiliser le style standard
            label_classes = "plugin-list-name"
        
        # Modifier le texte pour les séquences
        if original_is_sequence:
            # Désactiver l'interprétation du markup pour ce label
            # Supprimer le numéro pour les séquences
            # S'assurer que le nom est visible et non vide
            sequence_name = name if name else "Sans nom"
            logger.debug(f"Affichage de la séquence: {self.plugin_name} avec le nom: {sequence_name}")
            display_text = f"{icon} SÉQUENCE: {sequence_name}"
        else:
            # Affichage standard pour les plugins normaux
            display_text = f"{icon}  {name}"
            
        # Créer le label
        # Désactiver l'interprétation du markup pour éviter les problèmes avec les caractères spéciaux
        label = Label(display_text, classes=label_classes, markup=False)  # Afficher le nom et l'icône du plugin avec l'index
        
        yield label
        
        # Créer un ID pour le bouton de suppression
        # Créer un ID valide en remplaçant les caractères problématiques
        
        # Nettoyer le nom du plugin pour créer un ID valide
        # Remplacer les caractères spéciaux par des underscores
        if original_is_sequence:
            # Pour les séquences, utiliser un préfixe spécial
            safe_name = f"seq_{self.instance_id}"
        else:
            # Pour les plugins normaux, nettoyer le nom
            safe_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in self.plugin_name)
            # Éviter les ID trop longs
            if len(safe_name) > 20:
                safe_name = safe_name[:20]
            safe_name = f"{safe_name}_{self.instance_id}"
            
        button_id = f"remove_{safe_name}"
        
        # Ajouter une classe spéciale pour les boutons de suppression des séquences
        # Les plugins faisant partie d'une séquence ne sont pas supprimables individuellement
        if self.is_sequence:
            button_classes = "remove-button sequence-remove-button"
        elif self.is_part_of_sequence:
            # Masquer le bouton de suppression pour les plugins d'une séquence
            button_classes = "remove-button hidden"
        else:
            button_classes = "remove-button"
            
        yield Button("X", id=button_id, variant="error", classes=button_classes)  # Bouton pour retirer le plugin

    # Les styles sont maintenant définis dans le fichier TCSS