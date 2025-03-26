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

        # Ajouter un conteneur pour le checkbox
        with VerticalGroup(classes="checkbox-container"):
            # S'assurer que la valeur est bien un booléen
            if not isinstance(self.value, bool):
                if isinstance(self.value, str):
                    self.value = self.value.lower() in ('true', 't', 'yes', 'y', '1')
                else:
                    self.value = bool(self.value)
                    
            logger.debug(f"Création du checkbox {self.field_id} avec valeur {self.value}")
            
            self.checkbox = Checkbox(
                id=f"checkbox_{self.source_id}_{self.field_id}",
                value=self.value,
                classes="field-checkbox"
            )
            yield self.checkbox

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
