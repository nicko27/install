"""Directory field component for plugin configuration"""
import logging
from textual.app import ComposeResult
from textual.widgets import Button
from .text_field import TextField

logger = logging.getLogger('install_ui')

class DirectoryField(TextField):
    """Directory selection field with browse button"""
    
    def compose(self) -> ComposeResult:
        """Create the directory field with browse button"""
        yield from super().compose()
        yield Button("Browse...", id=f"browse_{self.field_id}")
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle browse button press"""
        if event.button.id == f"browse_{self.field_id}":
            # TODO: Implement directory browser
            # For now, just log that it was pressed
            logger.info(f"Browse button pressed for {self.field_id}")
            
    def _force_update_all_dependents(self, old_value, new_value):
        """Force update of all dependent fields"""
        logger.info(f"Forcing update of all fields depending on {self.field_id}")
        
        # Get fields_by_id from parent if not available
        if not self.fields_by_id and hasattr(self.parent, 'fields_by_id'):
            self.fields_by_id = self.parent.fields_by_id
            
        if not self.fields_by_id:
            logger.warning(f"No fields_by_id found for {self.field_id}, cannot update dependents")
            return
            
        # Find all dependent fields
        dependents = []
        for field_id, field in self.fields_by_id.items():
            if hasattr(field, 'field_config'):
                # Check various dependency types
                depends_on = field.field_config.get('depends_on')
                dynamic_options = field.field_config.get('dynamic_options', {})
                dynamic_default = field.field_config.get('dynamic_default', {})
                
                # Vérifier si le champ dépend de nous
                is_dependent = False

                # Dépendance directe
                if depends_on == self.field_id:
                    is_dependent = True

                # Dépendance via dynamic_options
                elif isinstance(dynamic_options, dict) and dynamic_options.get('script'):
                    # Vérifier dans les arguments
                    args = dynamic_options.get('args', [])
                    if any(isinstance(arg, dict) and arg.get('field') == self.field_id for arg in args):
                        is_dependent = True

                # Dépendance via dynamic_default
                elif isinstance(dynamic_default, dict) and dynamic_default.get('script'):
                    # Vérifier dans les arguments
                    args = dynamic_default.get('args', [])
                    if any(isinstance(arg, dict) and arg.get('field') == self.field_id for arg in args):
                        is_dependent = True

                if is_dependent:
                    dependents.append((field_id, field))
                    
        # Update each dependent field
        for field_id, field in dependents:
            logger.info(f"Updating dependent field {field_id}")
            
            try:
                # Mettre à jour l'état d'activation si nécessaire
                if hasattr(field, 'update_enabled_state'):
                    field.update_enabled_state()

                # Rafraîchir les options dynamiques si présent
                if hasattr(field, 'field_config') and 'dynamic_options' in field.field_config:
                    if hasattr(field, 'refresh_options'):
                        field.refresh_options()
                        logger.info(f"Successfully refreshed options for {field_id}")
                    else:
                        logger.warning(f"Field {field_id} has dynamic_options but no refresh_options method")

                # Rafraîchir la valeur par défaut dynamique si présent
                if hasattr(field, 'field_config') and 'dynamic_default' in field.field_config:
                    if hasattr(field, '_get_dynamic_default'):
                        new_value = field._get_dynamic_default()
                        if new_value is not None:
                            field.value = new_value
                            # Mettre à jour l'affichage si possible
                            if hasattr(field, 'refresh_display'):
                                field.refresh_display()
                    else:
                        logger.warning(f"Field {field_id} has dynamic_default but no _get_dynamic_default method")

            except Exception as e:
                logger.error(f"Error updating dependent field {field_id}: {e}")
                logger.error(traceback.format_exc())
