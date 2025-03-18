from textual.app import ComposeResult
from textual.widgets import Label, Checkbox
from textual.containers import Vertical, Horizontal, VerticalGroup, HorizontalGroup
from logging import getLogger

logger = getLogger('plugin_config_container')

from .config_container import ConfigContainer
from .text_field import TextField
from .directory_field import DirectoryField
from .ip_field import IPField
from .checkbox_field import CheckboxField
from .select_field import SelectField
from .checkbox_group_field import CheckboxGroupField
from .template_field import TemplateField
from .template_manager import TemplateManager



class PluginConfigContainer(ConfigContainer):
    """Conteneur pour les champs de configuration des plugins"""

    def __init__(self, plugin: str, name: str, icon: str, description: str,
                 fields_by_plugin: dict, fields_by_id: dict, config_fields: list, **kwargs):
        logger.debug(f"Initialisation du conteneur de configuration pour {plugin}")
        super().__init__(
            source_id=plugin,
            title=name,
            icon=icon,
            description=description,
            fields_by_id=fields_by_id,
            config_fields=config_fields,
            is_global=False,
            **kwargs
        )
        # Garder une référence aux collections de champs spécifiques au plugin
        self.fields_by_plugin = fields_by_plugin
        if plugin not in fields_by_plugin:
            fields_by_plugin[plugin] = {}
            logger.debug(f"Nouvelle collection de champs créée pour {plugin}")
        
        # Champ d'exécution distante (sera défini par PluginConfig si nécessaire)
        self.remote_field = None
        
        # Initialiser le gestionnaire de templates
        self.template_manager = TemplateManager()
        logger.debug(f"Gestionnaire de templates initialisé pour {plugin}")

    def compose(self) -> ComposeResult:
        """Compose le conteneur avec les champs et la case à cocher d'exécution distante si disponible"""
        logger.debug(f"Composition du conteneur pour {self.source_id}")
        
        # Titre et description
        with VerticalGroup(classes="config-header"):
            yield Label(f"{self.icon} {self.title}", classes="config-title")
            if self.description:
                yield Label(self.description, classes="config-description")

        if not self.config_fields and not self.remote_field:
            logger.debug(f"Aucun champ de configuration pour {self.source_id}")
            with VerticalGroup(classes="no-config"):
                with HorizontalGroup(classes="no-config-content"):
                    yield Label("ℹ️", classes="no-config-icon")
                    yield Label(f"Rien à configurer pour ce plugin", classes="no-config-label")
                return

        with VerticalGroup(classes="config-fields"):
            # Vérifier et ajouter le champ de template s'il y a des templates disponibles
            templates = self.template_manager.get_plugin_templates(self.source_id)
            if templates:
                logger.debug(f"Templates trouvés pour {self.source_id} : {list(templates.keys())}")
                template_field = TemplateField(self.source_id, 'template', self.fields_by_id)
                yield template_field
            else:
                logger.debug(f"Aucun template trouvé pour {self.source_id}")
            # Champs de configuration
            for field_config in self.config_fields:
                field_id = field_config.get('id')
                if not field_id:
                    logger.warning(f"Champ sans identifiant dans {self.source_id}")
                    continue
                    
                field_type = field_config.get('type', 'text')
                logger.debug(f"Création du champ {field_id} de type {field_type}")
                
                field_class = {
                    'text': TextField,
                    'directory': DirectoryField,
                    'ip': IPField,
                    'checkbox': CheckboxField,
                    'select': SelectField,
                    'checkbox_group': CheckboxGroupField
                }.get(field_type, TextField)

                # Créer le champ avec accès aux autres champs
                field = field_class(self.source_id, field_id, field_config, self.fields_by_id, is_global=self.is_global)
                self.fields_by_id[field_id] = field
                logger.debug(f"Champ {field_id} créé et ajouté au dictionnaire")

                # Si c'est une case à cocher, ajouter le gestionnaire d'événements
                if field_type in ['checkbox', 'checkbox_group']:
                    field.on_checkbox_changed = self.on_checkbox_changed
                    logger.debug(f"Gestionnaire d'événements ajouté pour {field_id}")

                yield field
            
            # Si nous avons un champ d'exécution distante, l'ajouter à la fin du conteneur
            if self.remote_field:
                logger.debug(f"Ajout du champ d'exécution distante pour {self.source_id}")
                with VerticalGroup(classes="remote-execution-container"):
                    yield self.remote_field

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Gère les changements d'état des cases à cocher avec suivi spécifique au plugin"""
        # Appeler d'abord l'implémentation parente
        super().on_checkbox_changed(event)

        # Gestion supplémentaire spécifique au plugin
        checkbox_id = event.checkbox.id
        logger.debug(f"Changement d'état de la case à cocher {checkbox_id}")

        for field_id, field in self.fields_by_id.items():
            if hasattr(field, 'source_id') and checkbox_id == f"checkbox_{field.source_id}_{field.field_id}":
                # Stocker dans la collection de champs spécifique au plugin
                self.fields_by_plugin[self.source_id][field_id] = field
                logger.debug(f"Champ {field_id} mis à jour dans la collection de {self.source_id}")
                break