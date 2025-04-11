from textual.app import ComposeResult
from textual.widgets import Checkbox
from textual.containers import VerticalGroup, HorizontalGroup
from typing import Dict, Any, Optional, Union, Tuple, List
import traceback

from .config_field import ConfigField
from ..utils.logging import get_logger

logger = get_logger('checkbox_field')

class CheckboxField(ConfigField):
    """
    Champ de configuration pour une case à cocher (booléen).
    
    Cette classe permet de créer un widget de case à cocher dans l'interface
    de configuration. Elle gère la conversion des valeurs en booléen,
    la notification des dépendances, et l'interaction avec les séquences.
    """

    def __init__(self, source_id: str, field_id: str, field_config: Dict[str, Any], 
                 fields_by_id: Optional[Dict[str, Any]] = None, is_global: bool = False,
                 instance_id: Optional[int] = None):
        """
        Initialise un champ de case à cocher.
        
        Args:
            source_id: ID du plugin ou de la source
            field_id: ID unique du champ
            field_config: Configuration du champ
            fields_by_id: Dictionnaire des champs par ID (pour les dépendances)
            is_global: Indique si le champ est global
            instance_id: ID d'instance (optionnel)
        """
        super().__init__(source_id, field_id, field_config, fields_by_id, is_global)
        
        # Initialiser la valeur à False par défaut
        self.value = False
        self.checkbox = None
        
        # Récupérer la valeur par défaut si définie
        if 'default' in self.field_config:
            self.value = self._ensure_boolean(self.field_config['default'])
            
        logger.debug(f"CheckboxField initialisé pour {source_id}.{field_id} avec valeur {self.value}")

    def compose(self) -> ComposeResult:
        """
        Compose l'interface du champ de case à cocher.
        
        Returns:
            ComposeResult: Résultat de la composition
        """
        try:
            # Composer les éléments communs depuis la classe parente
            yield from super().compose()
            
            # Essayer de charger la valeur depuis une séquence si disponible
            self._try_load_sequence_value()
            
            # S'assurer que la valeur est bien un booléen
            self.value = self._ensure_boolean(self.value)
            
            # Ajouter un conteneur pour la case à cocher
            with VerticalGroup(classes="checkbox-container"):
                logger.debug(f"Création du checkbox {self.field_id} avec valeur {self.value}")
                
                # Créer le widget Checkbox avec un ID unique pour le retrouver facilement
                self.checkbox = Checkbox(
                    id=f"checkbox_{self.source_id}_{self.field_id}",
                    value=self.value,
                    classes="field-checkbox"
                )
                yield self.checkbox
                
        except Exception as e:
            logger.error(f"Erreur lors de la composition du checkbox {self.field_id}: {e}")
            logger.error(traceback.format_exc())
            
            # En cas d'erreur, créer un widget minimal
            with VerticalGroup(classes="checkbox-container error"):
                yield Checkbox(
                    id=f"checkbox_{self.source_id}_{self.field_id}_error",
                    value=False,
                    disabled=True,
                    classes="field-checkbox error"
                )
    
    def _ensure_boolean(self, value: Any) -> bool:
        """
        Convertit une valeur en booléen de manière robuste.
        
        Args:
            value: Valeur à convertir en booléen
            
        Returns:
            bool: Valeur convertie en booléen
        """
        if value is None:
            return False
            
        if isinstance(value, bool):
            return value
            
        if isinstance(value, str):
            # Considérer différentes représentations textuelles d'un booléen
            return value.lower() in ('true', 't', 'yes', 'y', '1', 'on', 'enabled', 'active')
            
        # Pour les autres types, utiliser la conversion booléenne standard
        return bool(value)
            
    def _try_load_sequence_value(self) -> None:
        """
        Essaie de charger la valeur depuis une configuration de séquence.
        """
        try:
            # Trouver l'écran de configuration
            from .config_screen import PluginConfig
            config_screen = None
            
            # Rechercher l'écran de configuration dans la hiérarchie
            app = self.app if hasattr(self, 'app') and self.app else None
            if app and hasattr(app, 'screen') and isinstance(app.screen, PluginConfig):
                config_screen = app.screen
            
            if not config_screen or not hasattr(config_screen, 'current_config'):
                logger.debug(f"Pas d'écran de configuration trouvé pour {self.field_id}")
                return
            
            # Récupérer le conteneur parent
            from .plugin_config_container import PluginConfigContainer
            parent = self._get_parent_container()
            if not parent or not hasattr(parent, 'id'):
                logger.debug(f"Pas de conteneur parent trouvé pour {self.field_id}")
                return
            
            # Récupérer l'ID de l'instance du plugin
            plugin_instance_id = parent.id.replace('plugin_', '')
            if plugin_instance_id not in config_screen.current_config:
                logger.debug(f"Pas de configuration pour l'instance {plugin_instance_id}")
                return
                
            # Récupérer la configuration de la séquence
            sequence_config = config_screen.current_config[plugin_instance_id]
            
            # Déterminer le nom de la variable (utiliser variable_name si défini, sinon field_id)
            variable_name = getattr(self, 'variable_name', 
                                   self.field_config.get('variable', self.field_id))
            
            # Chercher la valeur dans la configuration
            value = None
            
            # Format 1: Chercher dans 'config' (nouveau format)
            if 'config' in sequence_config and variable_name in sequence_config['config']:
                value = sequence_config['config'][variable_name]
                logger.debug(f"Valeur trouvée dans séquence pour {variable_name}: {value}")
                    
            # Format 2: Chercher directement (ancien format)
            elif variable_name in sequence_config:
                value = sequence_config[variable_name]
                logger.debug(f"Valeur trouvée dans séquence (ancien format) pour {variable_name}: {value}")
            
            # Mettre à jour la valeur si trouvée
            if value is not None:
                # Conversion en booléen
                self.value = self._ensure_boolean(value)
                logger.debug(f"Valeur booléenne pour {self.field_id} définie à: {self.value}")
                    
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la valeur de séquence pour {self.field_id}: {e}")
            logger.error(traceback.format_exc())

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """
        Gère le changement d'état de la case à cocher.
        
        Args:
            event: Événement de changement
        """
        try:
            checkbox_id = f"checkbox_{self.source_id}_{self.field_id}"
            if event.checkbox.id == checkbox_id:
                old_value = self.value
                self.value = event.value
                
                logger.debug(f"Valeur de la checkbox {self.field_id} changée: {old_value} → {self.value}")
                
                # Mettre à jour le widget
                if hasattr(self, 'checkbox') and self.checkbox:
                    self.checkbox.value = self.value
                
                # Notifier les dépendances via la méthode améliorée
                self._notify_dependencies()
                
        except Exception as e:
            logger.error(f"Erreur lors du traitement du changement de case à cocher {self.field_id}: {e}")
            logger.error(traceback.format_exc())
    
    def get_value(self) -> bool:
        """
        Récupère la valeur actuelle de la case à cocher.
        
        Returns:
            bool: Valeur booléenne actuelle
        """
        return self.value
    
    def set_value(self, value: Any, update_dependencies: bool = True) -> bool:
        """
        Définit la valeur de la case à cocher.
        
        Args:
            value: Nouvelle valeur (sera convertie en booléen)
            update_dependencies: Si True, notifie les dépendances
            
        Returns:
            bool: True si la valeur a été mise à jour avec succès
        """
        try:
            # Convertir la valeur en booléen
            bool_value = self._ensure_boolean(value)
            
            # Si la valeur n'a pas changé, ne rien faire
            if self.value == bool_value:
                return True
                
            logger.debug(f"Définition de la valeur de {self.field_id}: {self.value} → {bool_value}")
            
            # Mettre à jour la valeur interne
            self.value = bool_value
            
            # Mettre à jour le widget si possible
            if hasattr(self, 'checkbox') and self.checkbox:
                self.checkbox.value = bool_value
                
            # Notifier les dépendances si demandé
            if update_dependencies:
                self._notify_dependencies()
                
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de la définition de la valeur pour {self.field_id}: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def validate_input(self, value: Any) -> Tuple[bool, str]:
        """
        Valide une valeur d'entrée.
        
        Args:
            value: Valeur à valider
            
        Returns:
            Tuple[bool, str]: (est_valide, message_erreur)
        """
        try:
            # Pour un checkbox, toute valeur est valide car convertible en booléen
            self._ensure_boolean(value)
            return True, ""
        except Exception as e:
            return False, f"Impossible de convertir en booléen: {e}"
    
    def _toggle_field_state(self, is_enabled: bool) -> None:
        """
        Active ou désactive le champ.
        
        Args:
            is_enabled: True pour activer, False pour désactiver
        """
        try:
            self.disabled = not is_enabled
            
            # Mettre à jour le widget
            if hasattr(self, 'checkbox') and self.checkbox:
                self.checkbox.disabled = not is_enabled
                
            logger.debug(f"État du champ {self.field_id} défini à: {'activé' if is_enabled else 'désactivé'}")
            
        except Exception as e:
            logger.error(f"Erreur lors du changement d'état du champ {self.field_id}: {e}")
            logger.error(traceback.format_exc())
    
    def _toggle_internal_widgets(self, is_enabled: bool) -> None:
        """
        Active ou désactive les widgets internes du champ.
        
        Args:
            is_enabled: True pour activer, False pour désactiver
        """
        try:
            if hasattr(self, 'checkbox') and self.checkbox:
                self.checkbox.disabled = not is_enabled
        except Exception as e:
            logger.error(f"Erreur lors du toggle des widgets internes de {self.field_id}: {e}")
    
    def _notify_dependencies(self) -> None:
        """
        Notifie les dépendances du changement de valeur.
        Utilise la méthode améliorée qui recherche le conteneur parent.
        """
        try:
            # Utiliser la méthode améliorée de récupération du conteneur parent
            parent = self._get_parent_container()
            
            if parent and hasattr(parent, 'update_dependent_fields'):
                logger.debug(f"Notification des dépendances depuis {self.unique_id}")
                parent.update_dependent_fields(self)
            else:
                logger.warning(f"Pas de conteneur parent avec update_dependent_fields trouvé pour {self.field_id}")
                
        except Exception as e:
            logger.error(f"Erreur lors de la notification des dépendances pour {self.field_id}: {e}")
            logger.error(traceback.format_exc())