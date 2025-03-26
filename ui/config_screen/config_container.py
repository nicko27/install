from textual.app import ComposeResult
from textual.containers import VerticalGroup, HorizontalGroup
from textual.widgets import Label, Input, Select, Button, Checkbox
from textual.reactive import reactive
from textual.widget import Widget

from .text_field import TextField
from .directory_field import DirectoryField
from .ip_field import IPField
from .checkbox_field import CheckboxField
from .select_field import SelectField
from .checkbox_group_field import CheckboxGroupField
from .password_field import PasswordField

from ..utils.logging import get_logger

logger = get_logger('config_container')

class ConfigContainer(VerticalGroup):
    """Base container for configuration fields (both plugins and global configs)"""
    # Define reactive attributes
    source_id = reactive("")       # Source identifier (plugin ID or global config ID)
    title = reactive("")           # Display name/title
    icon = reactive("")            # Display icon
    description = reactive("")     # Description
    is_global = reactive(False)    # Whether this is a global configuration

    def __init__(self, source_id: str, title: str, icon: str, description: str,
                 fields_by_id: dict, config_fields: list, is_global: bool = False, **kwargs):
        if "classes" in kwargs:
            if "config-container" not in kwargs["classes"]:
                kwargs["classes"] += " config-container"
        else:
            kwargs["classes"] = "config-container"

        super().__init__(**kwargs)
        # Set the reactive attributes
        self.source_id = source_id
        self.title = title
        self.icon = icon
        self.description = description
        self.is_global = is_global
        # Non-reactive attributes
        self.fields_by_id = fields_by_id
        self.config_fields = config_fields


    def compose(self) -> ComposeResult:
        # Title and description
        with VerticalGroup(classes="config-header"):
            yield Label(f"{self.icon} {self.title}", classes="config-title")
            if self.description:
                yield Label(self.description, classes="config-description")

        if not self.config_fields:
            with VerticalGroup(classes="no-config"):
                with HorizontalGroup(classes="no-config-content"):
                    yield Label("ℹ️", classes="no-config-icon")
                    yield Label(f"Rien à configurer pour ce plugin", classes="no-config-label")
                return

        with VerticalGroup(classes="config-fields"):
            # Configuration fields
            for field_config in self.config_fields:
                field_id = field_config.get('id')
                if not field_id:
                    logger.warning(f"Field without id in {self.source_id}")
                    continue
                field_type = field_config.get('type', 'text')
                field_class = {
                    'text': TextField,
                    'directory': DirectoryField,
                    'ip': IPField,
                    'checkbox': CheckboxField,
                    'select': SelectField,
                    'checkbox_group': CheckboxGroupField,
                    'password': PasswordField
                }.get(field_type, TextField)

                # Create field with access to other fields and whether it's global
                field = field_class(self.source_id, field_id, field_config, self.fields_by_id, is_global=self.is_global)
                self.fields_by_id[field_id] = field

                # If it's a checkbox or checkbox_group, add an event handler
                if field_type in ['checkbox', 'checkbox_group']:
                    field.on_checkbox_changed = self.on_checkbox_changed

                yield field

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox state changes"""
        # Find the field that emitted the event
        checkbox_id = event.checkbox.id
        logger.debug(f"Checkbox changed: {checkbox_id} -> {event.value}")

        # Parse field ID from checkbox ID
        for field_id, field in self.fields_by_id.items():
            if isinstance(field, CheckboxField) and checkbox_id == f"checkbox_{field.source_id}_{field.field_id}":
                logger.debug(f"Found matching checkbox field: {field.field_id}")
                field.value = event.value
                
                # Mettre à jour les champs qui dépendent de cette case à cocher
                self.update_dependent_fields(field)

                # La méthode update_dependent_fields sera appelée pour mettre à jour les champs dépendants
                break
    
    def update_dependent_fields(self, field):
        """Met à jour les champs qui dépendent d'un champ spécifique"""
        logger.debug(f"Mise à jour des champs dépendants de {field.field_id}")
        
        # Parcourir tous les champs pour trouver ceux qui dépendent de ce champ
        for dependent_field in self.fields_by_id.values():
            # Vérifier si le champ a une condition enabled_if qui dépend du champ actuel
            if hasattr(dependent_field, 'enabled_if') and dependent_field.enabled_if and dependent_field.enabled_if.get('field') == field.field_id:
                logger.debug(f"Champ dépendant trouvé: {dependent_field.field_id} avec enabled_if={dependent_field.enabled_if}")
                
                # Récupérer les valeurs pour la comparaison
                field_value = field.value
                required_value = dependent_field.enabled_if.get('value')
                
                # Convertir les valeurs en booléens si nécessaire pour la comparaison
                if isinstance(required_value, bool) and not isinstance(field_value, bool):
                    if isinstance(field_value, str):
                        field_value = field_value.lower() in ('true', 't', 'yes', 'y', '1')
                    else:
                        field_value = bool(field_value)
                
                # Déterminer si le champ doit être activé ou désactivé
                should_enable = field_value == required_value
                logger.debug(f"Champ {dependent_field.field_id}: should_enable={should_enable} (valeur={field_value}, valeur requise={required_value})")
                
                # Sauvegarder la valeur actuelle avant de désactiver le champ
                if hasattr(dependent_field, 'value'):
                    # Stocker la valeur actuelle dans un attribut temporaire
                    if not hasattr(dependent_field, '_saved_value') or dependent_field._saved_value is None:
                        dependent_field._saved_value = dependent_field.value
                        logger.debug(f"Valeur sauvegardée pour {dependent_field.field_id}: {dependent_field._saved_value}")
                
                # Trouver le widget à activer/désactiver
                for widget_type in [Input, Select, Button, Checkbox]:
                    try:
                        widget = dependent_field.query_one(widget_type)
                        logger.debug(f"Widget de type {widget_type.__name__} trouvé pour le champ {dependent_field.field_id}")
                        
                        # Toujours supprimer les classes existantes d'abord
                        dependent_field.remove_class('disabled')
                        dependent_field.disabled = False
                        widget.remove_class('disabled')
                        widget.disabled = False
                        
                        if not should_enable:
                            # Désactiver le champ mais sauvegarder sa valeur d'abord
                            logger.debug(f"Désactivation du widget pour le champ {dependent_field.field_id}")
                            
                            # Sauvegarder la valeur actuelle si elle n'est pas déjà sauvegardée
                            if hasattr(dependent_field, 'value') and not hasattr(dependent_field, '_saved_value'):
                                dependent_field._saved_value = dependent_field.value
                                logger.debug(f"Valeur sauvegardée lors de la désactivation pour {dependent_field.field_id}: {dependent_field._saved_value}")
                            
                            # Désactiver le champ
                            dependent_field.add_class('disabled')
                            dependent_field.disabled = True
                            widget.add_class('disabled')
                            widget.disabled = True
                        else:
                            # Activer le champ et restaurer sa valeur si nécessaire
                            logger.debug(f"Activation du widget pour le champ {dependent_field.field_id}")
                            
                            # Restaurer la valeur sauvegardée si elle existe
                            if hasattr(dependent_field, '_saved_value') and dependent_field._saved_value is not None:
                                logger.debug(f"Restauration de la valeur pour {dependent_field.field_id}: {dependent_field._saved_value}")
                                dependent_field.value = dependent_field._saved_value
                                
                                # Mettre à jour le widget avec la valeur restaurée
                                if hasattr(widget, 'value'):
                                    widget.value = dependent_field._saved_value
                                    
                                # Supprimer l'attribut _saved_value pour permettre de nouvelles modifications
                                delattr(dependent_field, '_saved_value')
                            # Sinon, utiliser la valeur par défaut
                            elif hasattr(dependent_field, 'value') and dependent_field.value is None:
                                # Essayer d'obtenir la valeur par défaut de la configuration du champ
                                if hasattr(dependent_field, 'field_config') and 'default' in dependent_field.field_config:
                                    default_value = dependent_field.field_config.get('default')
                                    logger.debug(f"Définition de la valeur par défaut pour le champ {dependent_field.field_id}: {default_value}")
                                    dependent_field.value = default_value
                                    
                                    # Mettre à jour le widget avec la valeur par défaut
                                    if hasattr(widget, 'value'):
                                        widget.value = default_value
                        
                        # Mettre à jour les champs qui dépendent de ce champ
                        self.update_dependent_fields(dependent_field)
                        break
                    except Exception as e:
                        continue