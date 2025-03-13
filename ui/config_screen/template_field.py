"""
Champ de sélection de template pour la configuration des plugins.
"""

from textual.widgets import Select, Label
from textual.widgets.vertical_scroll import VerticalScroll
from textual.app import ComposeResult
from logging import getLogger

logger = getLogger('template_field')
from .template_manager import TemplateManager



class TemplateField(VerticalGroup):
    """Champ de sélection de template"""

    def __init__(self, plugin_name: str, field_id: str, fields_by_id: dict):
        """
        Initialise le champ de sélection de template.

        Args:
            plugin_name: Nom du plugin
            field_id: Identifiant du champ
            fields_by_id: Dictionnaire des champs par ID
        """
        super().__init__()
        self.plugin_name = plugin_name
        self.field_id = field_id
        self.fields_by_id = fields_by_id
        self.template_manager = TemplateManager()
        logger.debug(f"Initialisation du champ de template pour {plugin_name}")
        self.templates = self.template_manager.get_plugin_templates(plugin_name)
        logger.debug(f"Templates chargés : {list(self.templates.keys())}")
        self.add_class("template-field")



    def compose(self) -> ComposeResult:
        """Compose le champ de sélection"""
        if not self.templates:
            logger.debug(f"Aucun template disponible pour {self.plugin_name}")
            return

        yield Label("Template de configuration:", classes="template-label")
        
        # Créer les options avec nom et description
        options = [(name, self.template_manager.get_template_description(self.plugin_name, name)) 
                  for name in self.template_manager.get_template_names(self.plugin_name)]
        
        # Créer le sélecteur avec l'option par défaut si disponible
        default_template = self.template_manager.get_default_template(self.plugin_name)
        select = Select(
            options=options,
            value='default' if default_template else None,
            id=f"template_{self.plugin_name}_{self.field_id}"
        )
        yield select

        # Appliquer le template par défaut si présent
        if default_template:
            logger.debug(f"Application du template par défaut pour {self.plugin_name}")
            self._apply_template('default')

    def _apply_template(self, template_name: str) -> None:
        """
        Applique un template aux champs de configuration.

        Args:
            template_name: Nom du template à appliquer
        """
        if template_name not in self.templates:
            logger.warning(f"Template {template_name} non trouvé pour {self.plugin_name}")
            return

        template = self.templates[template_name]
        variables = template['variables']

        # Mettre à jour les champs
        for field_name, value in variables.items():
            field_id = f"{self.plugin_name}_{field_name}"
            if field_id in self.fields_by_id:
                field = self.fields_by_id[field_id]
                if hasattr(field, 'value'):
                    field.value = str(value) if not isinstance(value, bool) else value
                    logger.debug(f"Champ {field_id} mis à jour avec la valeur : {value}")

    def on_select_changed(self, event: Select.Changed) -> None:
        """Gère le changement de template"""
        if event.value:
            logger.debug(f"Sélection du template {event.value} pour {self.plugin_name}")
            self._apply_template(event.value)
