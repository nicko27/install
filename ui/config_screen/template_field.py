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
        logger.info(f"Début de l'application du template {template_name} pour {self.plugin_name}")
        
        if template_name not in self.templates:
            logger.warning(f"Template {template_name} non trouvé pour {self.plugin_name}")
            return

        template = self.templates[template_name]
        variables = template['variables']
        logger.info(f"Variables du template {template_name}: {variables}")

        # Parcourir toutes les variables du template
        for var_name, var_value in variables.items():
            # Essayer plusieurs formats d'ID possibles
            possible_ids = [
                var_name,  # Juste le nom de la variable
                f"{self.plugin_name}_{var_name}",  # plugin_name_var_name
                f"{var_name}"  # var_name seul
            ]
            
            field = None
            used_id = None
            
            # Essayer chaque format d'ID possible
            for field_id in possible_ids:
                logger.info(f"Essai avec l'ID: {field_id}")
                if field_id in self.fields_by_id:
                    field = self.fields_by_id[field_id]
                    used_id = field_id
                    logger.info(f"Champ trouvé avec ID: {field_id}, type: {type(field).__name__}")
                    break
            
            # Si aucun champ n'a été trouvé, passer à la variable suivante
            if not field:
                logger.warning(f"Aucun champ trouvé pour la variable {var_name} avec les IDs testés: {possible_ids}")
                logger.debug(f"Clés disponibles dans fields_by_id: {list(self.fields_by_id.keys())}")
                continue
                
            # Convertir la valeur en chaîne si nécessaire
            new_value = str(var_value) if not isinstance(var_value, bool) else var_value
            logger.info(f"Tentative de mise à jour du champ {used_id} avec la valeur: {new_value} (type: {type(new_value).__name__})")
            
            try:
                # Mettre à jour l'attribut value du champ
                if hasattr(field, 'value'):
                    old_value = getattr(field, 'value', None)
                    logger.info(f"Champ {used_id} a un attribut 'value', valeur actuelle: {old_value}")
                    field.value = new_value
                    logger.info(f"Attribut value du champ {used_id} mis à jour avec succès: {new_value}")
                else:
                    logger.warning(f"Le champ {used_id} n'a pas d'attribut 'value'")
                    logger.debug(f"Attributs disponibles: {dir(field)}")
                    continue
                
                # Mettre à jour le widget UI correspondant
                if hasattr(field, 'input'):
                    field.input.value = new_value
                    logger.info(f"Widget input du champ {used_id} mis à jour avec succès")
                elif hasattr(field, 'select'):
                    # Pour les champs de type select, vérifier si la valeur est dans les options disponibles
                    if hasattr(field, 'options'):
                        available_values = [opt[1] for opt in field.options]
                        if new_value in available_values:
                            field.select.value = new_value
                            logger.info(f"Widget select du champ {used_id} mis à jour avec succès avec la valeur {new_value}")
                        else:
                            logger.warning(f"La valeur {new_value} n'est pas dans les options disponibles pour {used_id}: {available_values}")
                    else:
                        # Si nous n'avons pas accès aux options, essayer quand même de mettre à jour
                        field.select.value = new_value
                        logger.info(f"Widget select du champ {used_id} mis à jour avec succès (sans vérification d'options)")
                elif hasattr(field, 'checkbox'):
                    field.checkbox.value = bool(new_value)
                    logger.info(f"Widget checkbox du champ {used_id} mis à jour avec succès")
                else:
                    logger.warning(f"Aucun widget trouvé pour le champ {used_id}")
                    logger.debug(f"Attributs disponibles: {dir(field)}")
            except Exception as e:
                logger.error(f"Erreur lors de la mise à jour du champ {used_id}: {e}")
                logger.error(f"Détails de l'erreur: {type(e).__name__}: {str(e)}")
        
        logger.info(f"Fin de l'application du template {template_name} pour {self.plugin_name}")

    async def on_mount(self) -> None:
        """Méthode appelée lorsque le widget est monté"""
        # Récupérer le widget Select et s'abonner à son événement Changed
        try:
            select = self.query_one(f"#{self.select_id}", Select)
            logger.debug(f"Widget Select trouvé avec ID: {self.select_id}")
            
            # Utiliser on_select_changed directement comme gestionnaire d'événement
            select.on_changed = self.on_select_changed
            
            # Utiliser également watch comme méthode alternative pour s'assurer que l'événement est capturé
            self.watch(select, "changed", self._on_select_changed_watch)
            
            logger.debug(f"Événement 'changed' enregistré pour le widget Select avec deux méthodes")
            
            # Afficher les IDs des champs disponibles pour le débogage
            logger.debug(f"Clés disponibles dans fields_by_id: {list(self.fields_by_id.keys())}")
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement de l'événement: {e}")
            logger.error(f"Détails de l'erreur: {type(e).__name__}: {str(e)}")
    
    def on_select_changed(self, event: Select.Changed) -> None:
        """Gère le changement de template"""
        # Vérifier si l'événement a une valeur ou si c'est un objet Select
        if hasattr(event, 'value') and event.value:
            value = event.value
        elif hasattr(event, 'control') and event.control.value:
            value = event.control.value
        else:
            logger.warning(f"Événement de changement sans valeur valide: {event}")
            return
            
        logger.debug(f"Sélection du template {value} pour {self.plugin_name}")
        self._apply_template(value)
        
    def _on_select_changed_watch(self, event: Select.Changed) -> None:
        """Méthode alternative pour gérer le changement de template via watch"""
        logger.debug(f"Événement watch déclenché pour le template: {event}")
        # Déléguer à la méthode principale
        self.on_select_changed(event)
