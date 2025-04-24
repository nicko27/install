"""
Champ de sélection de template pour la configuration des plugins.
"""
from textual.containers import VerticalGroup
from textual.widgets import Select, Label
from textual.app import ComposeResult
from logging import getLogger
from typing import Dict, Any, List, Optional

from .template_manager import TemplateManager

logger = getLogger('template_field')

class TemplateField(VerticalGroup):
    """
    Champ de sélection de template pour la configuration des plugins.
    
    Permet à l'utilisateur de sélectionner un template prédéfini et de l'appliquer
    automatiquement aux autres champs de configuration.
    """

    def __init__(self, plugin_name: str, field_id: str, fields_by_id: Dict[str, Any]):
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
        self.add_class("template-field")
        
        # Charger les templates disponibles
        self.templates = self.template_manager.get_plugin_templates(plugin_name)
        logger.debug(f"Initialisation du champ de template pour {plugin_name} - {len(self.templates)} templates trouvés")
        
        # Initialiser l'ID du select (sera défini dans compose)
        self.select_id = f"template_{self.plugin_name}_{self.field_id}"
        
        # Stocker la sélection actuelle
        self.current_template = None

    def compose(self) -> ComposeResult:
        """
        Compose le champ de sélection de template.
        
        Returns:
            ComposeResult: Résultat de la composition
        """
        if not self.templates:
            logger.debug(f"Aucun template disponible pour {self.plugin_name}")
            yield Label("Aucun template disponible", classes="template-label no-templates")
            return

        yield Label("Template de configuration :", classes="template-label")
        
        # Créer les options avec nom et description
        options = self._get_template_options()
        
        # Créer le sélecteur avec l'option par défaut si disponible
        default_template_name = self._get_default_template_name()
        
        # Créer le widget Select avec un ID unique
        select_id = f"template_{self.plugin_name}_{self.field_id}"
        select = Select(
            options=options,
            value=default_template_name,
            id=select_id,
            classes="template-select"
        )
        
        # Stocker l'ID du select pour pouvoir le récupérer plus tard
        self.select_id = select_id
        self.current_template = default_template_name
        
        yield select

        # Appliquer le template par défaut si présent
        if default_template_name:
            logger.debug(f"Application du template par défaut '{default_template_name}' pour {self.plugin_name}")
            self._apply_template(default_template_name)

    def _get_template_options(self) -> List[tuple]:
        """
        Génère les options du sélecteur de template.
        
        Returns:
            List[tuple]: Liste de tuples (label, value) pour le widget Select
        """
        # Option spéciale pour "pas de template"
        options = [("-- Aucun template --", "")]
        
        # Ajouter les templates disponibles
        template_names = self.template_manager.get_template_names(self.plugin_name)
        
        for name in template_names:
            # Récupérer une description formatée pour l'affichage
            description = self._format_template_description(name)
            options.append((description, name))
            
        return options
        
    def _format_template_description(self, template_name: str) -> str:
        """
        Formate la description d'un template pour l'affichage.
        
        Args:
            template_name: Nom du template
            
        Returns:
            str: Description formatée
        """
        template = self.templates.get(template_name, {})
        
        # Utiliser le nom formaté ou le nom du fichier
        name = template.get('name', template_name)
        
        # Si c'est le template par défaut, l'indiquer
        if template_name == 'default':
            return f"{name} (défaut)"
        return name

    def _get_default_template_name(self) -> Optional[str]:
        """
        Détermine le template par défaut à sélectionner.
        
        Returns:
            Optional[str]: Nom du template par défaut ou None
        """
        # Vérifier si un template "default" existe
        if 'default' in self.templates:
            return 'default'
            
        # Sinon, utiliser le premier template disponible si la liste n'est pas vide
        template_names = list(self.templates.keys())
        if template_names:
            return template_names[0]
            
        # Aucun template disponible
        return None

    def _apply_template(self, template_name: str) -> None:
        """
        Applique un template aux champs de configuration.
        
        Args:
            template_name: Nom du template à appliquer
        """
        logger.info(f"Début de l'application du template '{template_name}' pour {self.plugin_name}")
        
        # Ignorer si aucun template n'est sélectionné
        if not template_name:
            logger.debug("Aucun template sélectionné, aucune action effectuée")
            return
            
        # Vérifier que le template existe
        if template_name not in self.templates:
            logger.warning(f"Template '{template_name}' non trouvé pour {self.plugin_name}")
            return

        # Récupérer les variables du template
        template = self.templates[template_name]
        variables = template.get('variables', {})
        
        if not variables:
            logger.warning(f"Template '{template_name}' ne contient aucune variable")
            return
            
        logger.info(f"Application de {len(variables)} variables du template '{template_name}'")

        # Liste des champs pour lesquels la mise à jour a réussi/échoué
        updated_fields = []
        failed_fields = []

        # Appliquer chaque variable aux champs correspondants
        for var_name, var_value in variables.items():
            # Tenter différentes stratégies pour trouver le champ correspondant
            field = self._find_matching_field(var_name)
            
            if field:
                # Tenter de mettre à jour le champ avec la nouvelle valeur
                success = self._update_field_value(field, var_value)
                if success:
                    updated_fields.append(var_name)
                else:
                    failed_fields.append(var_name)
            else:
                logger.warning(f"Aucun champ trouvé pour la variable '{var_name}'")
                failed_fields.append(var_name)
        
        # Journal des résultats
        if updated_fields:
            logger.info(f"Champs mis à jour avec succès: {', '.join(updated_fields)}")
        if failed_fields:
            logger.warning(f"Champs non mis à jour: {', '.join(failed_fields)}")

    def _find_matching_field(self, var_name: str) -> Optional[Any]:
        """
        Trouve le champ correspondant à une variable de template.
        
        Args:
            var_name: Nom de la variable
            
        Returns:
            Optional[Any]: Champ trouvé ou None
        """
        # Essayer différentes combinaisons pour trouver le champ
        possible_ids = [
            var_name,                      # Nom de variable seul
            f"{self.plugin_name}.{var_name}",  # plugin_name.var_name
            f"{var_name}"                  # var_name seul (doublon pour clarté)
        ]
        
        for field_id in possible_ids:
            if field_id in self.fields_by_id:
                logger.debug(f"Champ trouvé pour variable '{var_name}' avec ID: {field_id}")
                return self.fields_by_id[field_id]
                
        # Recherche par correspondance partielle
        for field_id, field in self.fields_by_id.items():
            if hasattr(field, 'variable_name') and field.variable_name == var_name:
                logger.debug(f"Champ trouvé pour variable '{var_name}' via variable_name dans {field_id}")
                return field
                
        logger.debug(f"Aucun champ trouvé pour variable '{var_name}' (IDs testés: {possible_ids})")
        return None

    def _update_field_value(self, field: Any, value: Any) -> bool:
        """
        Met à jour la valeur d'un champ de configuration.
        
        Args:
            field: Champ à mettre à jour
            value: Nouvelle valeur
            
        Returns:
            bool: True si la mise à jour a réussi
        """
        try:
            # Méthode 1: Utiliser set_value si disponible (méthode privilégiée)
            if hasattr(field, 'set_value'):
                field.set_value(value)
                logger.debug(f"Valeur mise à jour via set_value(): {value}")
                return True
                
            # Méthode 2: Modifier directement l'attribut value
            elif hasattr(field, 'value'):
                field.value = value
                logger.debug(f"Valeur mise à jour via attribut value: {value}")
                
                # Mettre à jour également le widget correspondant
                self._update_field_widget(field, value)
                return True
                
            else:
                logger.warning(f"Le champ ne possède ni set_value() ni attribut value")
                return False
                
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du champ: {e}")
            return False

    def _update_field_widget(self, field: Any, value: Any) -> None:
        """
        Met à jour le widget d'un champ avec la nouvelle valeur.
        
        Args:
            field: Champ dont le widget doit être mis à jour
            value: Nouvelle valeur
        """
        try:
            # Pour les différents types de widgets
            if hasattr(field, 'input'):
                field.input.value = str(value) if value is not None else ""
                logger.debug("Widget input mis à jour")
                
            elif hasattr(field, 'select'):
                # Pour les sélecteurs, vérifier si la valeur est dans les options
                if hasattr(field, 'options'):
                    available_values = [opt[1] for opt in field.options]
                    if str(value) in available_values:
                        field.select.value = str(value)
                        logger.debug("Widget select mis à jour")
                    else:
                        logger.warning(f"La valeur '{value}' n'est pas dans les options du select")
                else:
                    # Sans accès aux options, essayer quand même de mettre à jour
                    field.select.value = str(value)
                    logger.debug("Widget select mis à jour (sans vérification d'options)")
                    
            elif hasattr(field, 'checkbox'):
                field.checkbox.value = bool(value)
                logger.debug("Widget checkbox mis à jour")
                
            else:
                logger.debug("Aucun widget reconnu trouvé pour la mise à jour")
                
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du widget: {e}")

    async def on_mount(self) -> None:
        """
        Méthode appelée lorsque le widget est monté dans l'interface.
        """
        try:
            # Récupérer le widget Select et configurer les gestionnaires d'événements
            select = self.query_one(f"#{self.select_id}", Select)
            logger.debug(f"Widget Select trouvé avec ID: {self.select_id}")
            
            # Utiliser les deux méthodes complémentaires pour être sûr de capturer l'événement
            select.on_changed = self.on_select_changed
            self.watch(select, "changed", self._on_select_changed_watch)
            
            # Sélectionner "Aucun template" par défaut (valeur vide)
            logger.debug("Sélection de 'Aucun template' par défaut")
            select.value = ""
            
            # Réinitialiser explicitement les champs aux valeurs par défaut
            # pour s'assurer que les valeurs des templates ne sont pas appliquées
            logger.debug("Réinitialisation explicite des champs aux valeurs par défaut lors du montage")
            self.call_after_refresh(self._reset_fields_to_defaults)
            
            logger.debug("Gestionnaires d'événements configurés pour le sélecteur de template")
        except Exception as e:
            logger.error(f"Erreur lors de la configuration des événements: {e}")

    def on_select_changed(self, event: Select.Changed) -> None:
        """
        Gère le changement de template sélectionné.
        
        Args:
            event: Événement de changement du Select
        """
        # Extraire la valeur de l'événement
        value = None
        if hasattr(event, 'value'):
            value = event.value
        elif hasattr(event, 'select') and hasattr(event.select, 'value'):
            value = event.select.value
        
        logger.debug(f"Template sélectionné pour {self.plugin_name}: {value}")
        
        # Mettre à jour la sélection actuelle
        self.current_template = value
        
        # Si "Aucun template" est sélectionné (valeur vide), réinitialiser les champs à leurs valeurs par défaut
        if not value:
            logger.debug("Aucun template sélectionné, réinitialisation des champs aux valeurs par défaut")
            self._reset_fields_to_defaults()
        else:
            # Appliquer le template sélectionné
            self._apply_template(value)
        
    def _on_select_changed_watch(self, event: Select.Changed) -> None:
        """
        Méthode alternative pour gérer le changement via watch.
        
        Args:
            event: Événement de changement du Select
        """
        logger.debug(f"Événement watch déclenché pour le template")
        # Déléguer à la méthode principale
        self.on_select_changed(event)
        
    def _reset_fields_to_defaults(self) -> None:
        """
        Réinitialise tous les champs du plugin à leurs valeurs par défaut.
        Cette méthode est appelée lorsque l'option "Aucun template" est sélectionnée.
        """
        logger.info(f"Réinitialisation des champs aux valeurs par défaut pour {self.plugin_name}")
        
        # Récupérer tous les champs du plugin
        plugin_fields = {}
        for field_id, field in self.fields_by_id.items():
            if hasattr(field, 'source_id') and field.source_id == self.plugin_name:
                plugin_fields[field_id] = field
                
        if not plugin_fields:
            logger.warning(f"Aucun champ trouvé pour le plugin {self.plugin_name}")
            return
            
        logger.debug(f"Réinitialisation de {len(plugin_fields)} champs pour {self.plugin_name}")
        
        # Pour chaque champ, réinitialiser à la valeur par défaut
        for field_id, field in plugin_fields.items():
            try:
                # Ignorer le champ de template lui-même
                if field_id == 'template' or field == self:
                    continue
                    
                # Utiliser la méthode restore_default si disponible
                if hasattr(field, 'restore_default'):
                    logger.debug(f"Appel de restore_default() pour le champ {field_id}")
                    success = field.restore_default()
                    if not success:
                        logger.warning(f"Échec de restore_default() pour {field_id}")
                # Sinon, essayer d'accéder à default_value
                elif hasattr(field, 'default_value'):
                    logger.debug(f"Réinitialisation du champ {field_id} à la valeur par défaut: {field.default_value}")
                    field.value = field.default_value
                # Sinon, essayer d'accéder à field_config['default']
                elif hasattr(field, 'field_config') and 'default' in field.field_config:
                    default_value = field.field_config['default']
                    logger.debug(f"Réinitialisation du champ {field_id} à la valeur par défaut de la config: {default_value}")
                    if hasattr(field, 'set_value'):
                        field.set_value(default_value, update_input=True, update_dependencies=True)
                    else:
                        field.value = default_value
                else:
                    logger.warning(f"Impossible de réinitialiser le champ {field_id}, aucune méthode disponible")
            except Exception as e:
                logger.error(f"Erreur lors de la réinitialisation du champ {field_id}: {e}")
                
        # Mettre à jour les dépendances entre champs
        if hasattr(self, 'parent') and hasattr(self.parent, 'update_all_dependencies'):
            logger.debug("Mise à jour des dépendances entre champs")
            self.parent.update_all_dependencies()