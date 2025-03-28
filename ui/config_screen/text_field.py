from textual.app import ComposeResult
from textual.widgets import Input
from textual.containers import VerticalGroup, HorizontalGroup
from .config_field import ConfigField
from ..utils.logging import get_logger

logger = get_logger('text_field')

class TextField(ConfigField):
    """Text input field"""
    
    def __init__(self, source_id: str, field_id: str, field_config: dict, fields_by_id: dict = None, is_global: bool = False):
        super().__init__(source_id, field_id, field_config, fields_by_id, is_global)
        self._updating = False  # Flag pour éviter les mises à jour récursives
    def compose(self) -> ComposeResult:
        yield from super().compose()
        with VerticalGroup(classes="input-container"):
            self.input = Input(
                placeholder=self.field_config.get('placeholder', ''),
                value=self.value or '',
                id=f"input_{self.field_id}"
            )
            # Always initialize to enabled state first
            self.input.disabled = False
            self.input.remove_class('disabled')

            if self.disabled:
                logger.debug(f"TextField {self.field_id} is initially disabled")
                self.input.disabled = True
                self.input.add_class('disabled')
            yield self.input

    def validate_input(self, value: str) -> tuple[bool, str]:
        """Validate input value according to configured rules"""
        # Vérifier si le champ est désactivé par enabled_if
        if self.enabled_if and self.disabled:
            return True, ""

        # Vérifier not_empty
        if self.field_config.get('not_empty', False) and not value:
            return False, "Ce champ ne peut pas être vide"

        # Vérifier min_length
        min_length = self.field_config.get('min_length')
        if min_length and len(value) < min_length:
            return False, f"La longueur minimale est de {min_length} caractères"

        # Vérifier max_length
        max_length = self.field_config.get('max_length')
        if max_length and len(value) > max_length:
            return False, f"La longueur maximale est de {max_length} caractères"

        # Vérifier no_spaces
        if self.field_config.get('validate') == 'no_spaces' and ' ' in value:
            return False, "Les espaces ne sont pas autorisés"

        return True, ""

    def set_value(self, value: str, update_input: bool = True, update_dependencies: bool = True) -> None:
        """Set the value of the field and optionally update the input widget and dependencies"""
        logger.debug(f"Setting value for field {self.field_id} to '{value}' (update_input={update_input}, update_dependencies={update_dependencies})")
        
        # Si on est déjà en train de mettre à jour, ne pas faire de mise à jour récursive
        if self._updating:
            logger.debug(f"Déjà en cours de mise à jour pour {self.field_id}, on ignore")
            return True
            
        self._updating = True
        
        # Ensure value is a string
        value = str(value) if value is not None else ""

        # Validation
        is_valid, error_msg = self.validate_input(value)
        logger.debug(f"Validation result for {self.field_id}: valid={is_valid}, error={error_msg if not is_valid else 'None'}")
        
        if not is_valid:
            if update_input:
                logger.debug(f"Adding error class to {self.field_id} input")
                self.input.add_class('error')
                self.input.tooltip = error_msg
            return False
        else:
            if update_input:
                logger.debug(f"Removing error class from {self.field_id} input")
                self.input.remove_class('error')
                self.input.tooltip = None

        # Update internal value
        logger.debug(f"Updating internal value for {self.field_id} from '{self.value}' to '{value}'")
        self.value = value
        
        # Update input widget if requested
        if update_input:
            logger.debug(f"Updating input widget value for {self.field_id} to '{value}'")
            self.input.value = value

        # Update dependencies if requested
        if update_dependencies:
            logger.debug(f"Looking for parent container to update dependencies for {self.field_id}")
            from .config_container import ConfigContainer
            parent = next((ancestor for ancestor in self.ancestors_with_self if isinstance(ancestor, ConfigContainer)), None)
            if parent:
                logger.debug(f"Found parent container for {self.field_id}, updating dependencies")
                parent.update_dependent_fields(self)
            else:
                logger.debug(f"No parent container found for {self.field_id}")
                
        self._updating = False
        return True

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes"""
        if event.input.id == f"input_{self.field_id}":
            # Use set_value but don't update the input widget since it's already updated
            self.set_value(event.value, update_input=False)