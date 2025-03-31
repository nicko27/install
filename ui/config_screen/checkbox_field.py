from textual.app import ComposeResult
from textual.widgets import Checkbox
from textual.containers import VerticalGroup, HorizontalGroup
from .config_field import ConfigField

from ..utils.logging import get_logger

logger = get_logger('checkbox_field')

class CheckboxField(ConfigField):
    """Checkbox field"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        
        # Essayer de récupérer la valeur depuis la séquence avant de créer le widget
        self._try_load_sequence_value()

        # Ajouter un conteneur pour le checkbox
        with VerticalGroup(classes="checkbox-container"):
            # S'assurer que la valeur est bien un booléen
            if not isinstance(self.value, bool):
                if isinstance(self.value, str):
                    self.value = self.value.lower() in ('true', 't', 'yes', 'y', '1')
                else:
                    self.value = bool(self.value)
                    
            logger.debug(f"💻 Création du checkbox {self.field_id} avec valeur {self.value}")
            
            self.checkbox = Checkbox(
                id=f"checkbox_{self.source_id}_{self.field_id}",
                value=self.value,
                classes="field-checkbox"
            )
            yield self.checkbox
            
    def _try_load_sequence_value(self):
        """Essaie de charger la valeur depuis la configuration prédéfinie (séquence)"""
        try:
            # Trouver l'écran de configuration
            from .config_screen import PluginConfig
            config_screen = None
            
            # Rechercher l'écran de configuration dans la hiérarchie des ancêtres
            app = self.app if hasattr(self, 'app') and self.app else None
            if app and hasattr(app, 'screen') and isinstance(app.screen, PluginConfig):
                config_screen = app.screen
            
            if not config_screen or not hasattr(config_screen, 'current_config'):
                return
            
            # Récupérer le conteneur parent
            from .plugin_config_container import PluginConfigContainer
            parent = next((a for a in self.ancestors_with_self if isinstance(a, PluginConfigContainer)), None)
            if not parent or not hasattr(parent, 'id'):
                return
            
            # Récupérer l'ID de l'instance du plugin
            plugin_instance_id = parent.id.replace('plugin_', '')
            if plugin_instance_id not in config_screen.current_config:
                return
                
            # Récupérer la configuration prédéfinie
            predefined_config = config_screen.current_config[plugin_instance_id]
            
            # Obtenir la variable ou config, selon le format
            variable_name = self.field_config.get('variable', self.field_id)
            
            value = None
            
            # Chercher dans 'config' (nouveau format)
            if 'config' in predefined_config and variable_name in predefined_config['config']:
                value = predefined_config['config'][variable_name]
                logger.debug(f"💾 Valeur trouvée dans séquence pour {self.field_id}: {value}")
                    
            # Format 2: Chercher directement (ancien format)
            elif variable_name in predefined_config:
                value = predefined_config[variable_name]
                logger.debug(f"💾 Valeur trouvée dans séquence (ancien format) pour {self.field_id}: {value}")
            
            # Mettre à jour la valeur si trouvée
            if value is not None:
                # Conversion en booléen
                if isinstance(value, str):
                    self.value = value.lower() in ('true', 't', 'yes', 'y', '1')
                else:
                    self.value = bool(value)
                logger.debug(f"💾 Valeur booléenne pour {self.field_id} définie à: {self.value}")
                    
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la valeur de séquence pour {self.field_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == f"checkbox_{self.source_id}_{self.field_id}":
            old_value = self.value
            self.value = event.value
            logger.debug(f"Valeur de la checkbox {self.field_id} changée de {old_value} à {self.value}")
            
            # Notifier les containers parents du changement pour mettre à jour les dépendances
            parent = self.parent
            while parent:
                if hasattr(parent, 'update_dependent_fields'):
                    parent.update_dependent_fields(self)
                    break
                parent = parent.parent
    
    def get_value(self):
        """Récupère la valeur actuelle de la checkbox"""
        return self.value
    
    def set_value(self, value):
        """Définit la valeur de la checkbox"""
        # Convertir la valeur en booléen si nécessaire
        if not isinstance(value, bool):
            if isinstance(value, str):
                value = value.lower() in ('true', 't', 'yes', 'y', '1')
            else:
                value = bool(value)
                
        logger.debug(f"Définition de la valeur de la checkbox {self.field_id} à {value}")
        
        # Mettre à jour la valeur interne
        self.value = value
        
        # Mettre à jour le widget
        if hasattr(self, 'checkbox'):
            self.checkbox.value = value
            
        return True
