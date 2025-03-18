"""
Champ de sélection de template pour la configuration des plugins.
"""
from textual.containers import VerticalGroup
from textual.widgets import Select, Label
from textual.app import ComposeResult
from logging import getLogger
from .template_manager import TemplateManager

logger = getLogger('template_field')


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
        
        # Initialiser l'ID du select (sera défini dans compose)
        self.select_id = f"template_{self.plugin_name}_{self.field_id}"



    def compose(self) -> ComposeResult:
        """Compose le champ de sélection"""
        if not self.templates:
            logger.debug(f"Aucun template disponible pour {self.plugin_name}")
            return

        yield Label("Template de configuration:", classes="template-label")
        
        # Créer les options avec nom et description
        options = [(self.template_manager.get_template_description(self.plugin_name, name), name) 
                  for name in self.template_manager.get_template_names(self.plugin_name)]
        
        # Créer le sélecteur avec l'option par défaut si disponible
        default_template_data = self.template_manager.get_default_template(self.plugin_name)
        default_template_name = 'default' if default_template_data else None
        
        # Créer le widget Select avec un ID unique
        select_id = f"template_{self.plugin_name}_{self.field_id}"
        select = Select(
            options=options,
            value=default_template_name,
            id=select_id
        )
        
        # Stocker l'ID du select pour pouvoir le récupérer plus tard
        self.select_id = select_id
        
        yield select

        # Appliquer le template par défaut si présent
        if default_template_name:
            logger.debug(f"Application du template par défaut pour {self.plugin_name}")
            self._apply_template(default_template_name)

    def _apply_template(self, template_name: str) -> None:
        """
        Applique un template aux champs de configuration.
        Si une variable est manquante dans le template, utilise la valeur par défaut du settings.yml.

        Args:
            template_name: Nom du template à appliquer
        """
        if template_name not in self.templates:
            logger.warning(f"Template {template_name} non trouvé pour {self.plugin_name}")
            return

        template = self.templates[template_name]
        variables = template['variables']

        # Collecter tous les champs disponibles pour ce plugin
        plugin_fields = {}
        for field_id, field in self.fields_by_id.items():
            if field_id.startswith(f"{self.plugin_name}_"):
                field_name = field_id[len(self.plugin_name) + 1:]
                plugin_fields[field_name] = field
        
        # Mettre à jour les champs avec les valeurs du template
        for field_name, field in plugin_fields.items():
            # Vérifier si la variable existe dans le template
            if field_name in variables:
                value = variables[field_name]
                if hasattr(field, 'value'):
                    field.value = str(value) if not isinstance(value, bool) else value
                    logger.debug(f"Champ {field_name} mis à jour avec la valeur du template : {value}")
            else:
                # Si la variable n'existe pas dans le template, conserver la valeur par défaut
                logger.debug(f"Variable {field_name} non trouvée dans le template, conservation de la valeur par défaut")

    async def on_mount(self) -> None:
        """Méthode appelée lorsque le widget est monté"""
        # Récupérer le widget Select et s'abonner à son événement Changed
        try:
            select = self.query_one(f"#{self.select_id}", Select)
            logger.debug(f"Widget Select trouvé avec ID: {self.select_id}")
            self.watch(select, "changed", self.on_select_changed)
            logger.debug(f"Événement 'changed' enregistré pour le widget Select")
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement de l'événement: {e}")
    
    def on_select_changed(self, event: Select.Changed) -> None:
        """Gère le changement de template"""
        if event.value:
            logger.debug(f"Sélection du template {event.value} pour {self.plugin_name}")
            self._apply_template(event.value)
