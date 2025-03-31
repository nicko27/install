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
    
    def update_dependent_fields(self, source_field):
        """Met à jour les champs qui dépendent d'un champ spécifique, avec prévention des cycles de mise à jour"""
        # Protection contre les appels récursifs en cours de traitement
        if hasattr(self, '_updating_dependencies') and self._updating_dependencies:
            logger.debug(f"⚠️ Mise à jour des dépendances déjà en cours, ignorant l'appel pour {source_field.field_id}")
            return
            
        try:
            # Marquer le début de la mise à jour pour éviter les cycles
            self._updating_dependencies = True
            
            logger.debug(f"🔄 DÉBUT mise à jour des champs dépendants de {source_field.field_id} (valeur={source_field.value})")
            # Liste de tous les IDs de champs disponibles pour le log
            field_ids = sorted([f.field_id for f in self.fields_by_id.values()])
            logger.debug(f"Champs disponibles: {field_ids}")
            
            # 1. Créer une copie de la liste des champs pour l'itération
            dependent_fields = list(self.fields_by_id.values())
            fields_to_remove = []
            
            for dependent_field in dependent_fields:
                # Ignorer le champ source et les champs déjà traités ce cycle
                if dependent_field.field_id == source_field.field_id or hasattr(dependent_field, '_processed_in_cycle'):
                    continue
                    
                logger.debug(f"🔍 Analyse des dépendances pour {dependent_field.field_id}")
                
                # 2. TRAITEMENT DES DÉPENDANCES DEPENDS_ON (options dynamiques)
                # Ces champs changent leurs options selon la valeur d'un autre champ
                has_depends_on = hasattr(dependent_field, 'depends_on')
                depends_on_match = has_depends_on and dependent_field.depends_on == source_field.field_id
                
                if depends_on_match and hasattr(dependent_field, 'update_dynamic_options'):
                    logger.debug(f"✅ Champ avec options dynamiques trouvé: {dependent_field.field_id}")
                    
                    # Marquer ce champ comme traité dans ce cycle
                    dependent_field._processed_in_cycle = True
                    
                    # Sauvegarder l'ancienne valeur pour vérifier si elle change
                    old_value = getattr(dependent_field, 'value', None)
                    
                    # Mettre à jour les options dynamiques
                    dependent_field.update_dynamic_options()
                    
                    # Si après mise à jour le champ n'a plus d'options, le marquer pour suppression
                    has_options = hasattr(dependent_field, 'options')
                    options_empty = has_options and (dependent_field.options is None or len(dependent_field.options) == 0)
                    
                    if options_empty:
                        logger.debug(f"❌ {dependent_field.field_id} n'a plus d'options valides")
                        fields_to_remove.append(dependent_field)
                    elif old_value != dependent_field.value:
                        logger.debug(f"🔄 La valeur de {dependent_field.field_id} a changé: {old_value} -> {dependent_field.value}")
                
                # 3. TRAITEMENT DES CONDITIONS ENABLED_IF
                # Ces champs sont activés/désactivés selon la valeur d'un autre champ
                has_enabled_if = (hasattr(dependent_field, 'enabled_if') and 
                                  dependent_field.enabled_if and 
                                  dependent_field.enabled_if.get('field') == source_field.field_id)
                
                if has_enabled_if:
                    # Marquer ce champ comme traité dans ce cycle
                    dependent_field._processed_in_cycle = True
                    
                    field_value = source_field.value
                    required_value = dependent_field.enabled_if.get('value')
                    
                    # Normaliser les valeurs booléennes pour comparaison
                    if isinstance(required_value, bool) and not isinstance(field_value, bool):
                        if isinstance(field_value, str):
                            field_value = field_value.lower() in ('true', 't', 'yes', 'y', '1')
                        else:
                            field_value = bool(field_value)
                    
                    # Est-ce que le champ doit être activé ou désactivé?
                    should_enable = field_value == required_value
                    
                    if not should_enable:
                        logger.debug(f"❌ Condition non remplie pour {dependent_field.field_id} (valeur={field_value}, requise={required_value})")
                        fields_to_remove.append(dependent_field)
                    else:
                        logger.debug(f"✅ Condition remplie pour {dependent_field.field_id}")
                        
                        # Sauvegarder la valeur actuelle avant réactivation
                        if hasattr(dependent_field, 'value') and (
                            not hasattr(dependent_field, '_saved_value') or dependent_field._saved_value is None
                        ):
                            dependent_field._saved_value = dependent_field.value
                        
                        # Réactiver le widget et restaurer sa valeur
                        self._restore_field_state(dependent_field)
            
            # 4. SUPPRIMER LES CHAMPS INVALIDÉS de l'interface
            for field_to_remove in fields_to_remove:
                logger.debug(f"🗑️ Suppression du champ {field_to_remove.field_id} de l'interface")
                
                # Supprimer du dictionnaire des champs
                if field_to_remove.field_id in self.fields_by_id:
                    del self.fields_by_id[field_to_remove.field_id]
                
                # Supprimer le widget de l'interface
                if field_to_remove in self.children:
                    field_to_remove.remove()
                    
            logger.debug(f"✓ FIN mise à jour des dépendances pour {source_field.field_id}")
        
        except Exception as e:
            logger.error(f"❌ ERREUR lors de la mise à jour des dépendances: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        finally:
            # Toujours nettoyer les marqueurs de cycle et le flag de mise à jour
            self._updating_dependencies = False
            # Nettoyer les indicateurs de traitement pour tous les champs
            for field in self.fields_by_id.values():
                if hasattr(field, '_processed_in_cycle'):
                    delattr(field, '_processed_in_cycle')
    
    def _restore_field_state(self, field):
        """Restaure l'état d'un champ désactivé"""
        logger.debug(f"🔄 Restauration de l'état du champ {field.field_id}")
        
        # Rechercher tous les widgets d'interaction à réactiver
        for widget_type in [Input, Select, Button, Checkbox]:
            try:
                widget = field.query_one(widget_type)
                
                # Réactiver le widget et son conteneur
                field.remove_class('disabled')
                field.disabled = False
                widget.remove_class('disabled')
                widget.disabled = False
                
                # Restaurer la valeur sauvegardée si disponible
                if hasattr(field, '_saved_value') and field._saved_value is not None:
                    logger.debug(f"📝 Restauration de la valeur pour {field.field_id}: {field._saved_value}")
                    # Utiliser set_value avec update_dependencies=False pour éviter les cycles
                    if hasattr(field, 'set_value'):
                        field.set_value(field._saved_value, update_dependencies=False)
                    else:
                        field.value = field._saved_value
                        
                # Widget trouvé et traité, on peut sortir
                return True
            except Exception:
                # Widget de ce type non trouvé, continuer avec le suivant
                pass
                
        # Aucun widget interactif trouvé
        logger.warning(f"⚠️ Aucun widget interactif trouvé pour {field.field_id}")
        return False