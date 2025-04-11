# ui/config_screen/plugin_config_container.py
from textual.app import ComposeResult
from textual.containers import VerticalGroup, Horizontal, Vertical, Container
from textual.widgets import Label, Button, Input, Select, Checkbox
from typing import Dict, List, Any, Optional, Set, Tuple, Union, Callable
import os
import re
import traceback
import time
import logging

from .config_container import ConfigContainer
from .config_field import ConfigField
from .checkbox_field import CheckboxField
from .checkbox_group_field import CheckboxGroupField
from .template_manager import TemplateManager
from ..utils.logging import get_logger

logger = get_logger('plugin_config_container')

class PluginConfigContainer(ConfigContainer):
    """
    Conteneur de configuration spécifique pour les plugins.
    
    Cette classe étend ConfigContainer pour gérer les spécificités des plugins,
    notamment les templates, les instances multiples, et l'exécution à distance.
    """

    def __init__(self, source_id: str, instance_id: Optional[int] = None,
                fields_by_id: Optional[Dict[str, Any]] = None,
                config_fields: Optional[List[Dict[str, Any]]] = None,
                is_global: bool = False):
        """
        Initialise un conteneur de configuration pour un plugin.

        Args:
            source_id: ID du plugin
            instance_id: ID d'instance du plugin (pour les instances multiples)
            fields_by_id: Dictionnaire global des champs indexés par ID
            config_fields: Liste des configurations de champs pour ce plugin
            is_global: Indique si c'est un conteneur global
        """
        super().__init__(source_id, instance_id)
        
        # Attributs de base
        self.title = source_id
        self.icon = "📦"
        self.description = ""
        self.is_global = is_global
        self.is_enabled = True
        
        # Initialiser le gestionnaire de templates
        self.template_manager = TemplateManager()
        
        # Structures pour le suivi des valeurs et des états
        self._applied_values = {}
        self._pending_values = {}
        self._field_errors = {}
        self._field_retry_counts = {}
        self._is_updating_values = False
        self._max_retry_attempts = 3
        
        # Stocker les champs globaux si fournis
        if fields_by_id:
            self.fields_by_id = fields_by_id
            
        # Analyser les dépendances si les configurations sont fournies
        if config_fields:
            self._analyze_field_dependencies(config_fields)
            self._analyze_plugin_dependencies(config_fields)
            
        logger.debug(f"PluginConfigContainer initialisé pour {source_id} (instance: {instance_id})")

    def compose(self) -> ComposeResult:
        """
        Compose l'interface du conteneur de configuration du plugin.

        Returns:
            ComposeResult: Résultat de la composition
        """
        try:
            # En-tête du plugin
            yield Label(f"{self.icon} {self.title}", classes="plugin-header")
            
            if self.description:
                yield Label(self.description, classes="plugin-description")
                
            # Zone pour les champs de configuration
            config_area = Container(classes="plugin-config-fields")
            
            # Créer les champs à partir des définitions et les ajouter au config_area
            if hasattr(self, 'fields_by_id') and self.fields_by_id:
                # Importer les classes de champs nécessaires
                from .text_field import TextField
                from .directory_field import DirectoryField
                from .ip_field import IPField
                from .select_field import SelectField
                from .checkbox_field import CheckboxField
                from .password_field import PasswordField
                
                logger.debug(f"Création des champs pour {self.source_id}")
                
                # Trier les champs par leur ID pour un ordre cohérent
                field_ids = sorted(self.fields_by_id.keys())
                for field_id in field_ids:
                    field = self.fields_by_id[field_id]
                    # Ne monter que les champs appartenant à ce plugin
                    if hasattr(field, 'source_id') and field.source_id == self.source_id:
                        logger.debug(f"Ajout du champ {field_id} au config_area")
                        config_area.mount(field)
            else:
                logger.warning(f"Aucun champ à afficher pour {self.source_id}")
                config_area.mount(Label("Aucun champ de configuration disponible", classes="no-fields"))
                
            yield config_area
            
            # Template selector si disponible
            if self._has_templates():
                with Horizontal(classes="template-selector"):
                    yield Label("Template:", classes="template-label")
                    yield Select(
                        self._get_template_options(),
                        id=f"template_{self.source_id}_{self.instance_id}",
                        classes="template-select"
                    )
                    yield Button("Appliquer", id=f"apply_template_{self.source_id}_{self.instance_id}")
                    
            logger.debug(f"Interface composée pour {self.source_id} (instance: {self.instance_id})")
                
        except Exception as e:
            logger.error(f"Erreur lors de la composition de l'interface pour {self.source_id}: {e}")
            logger.error(traceback.format_exc())
            # Fournir une interface minimale en cas d'erreur
            yield Label(f"Erreur de chargement pour {self.source_id}", classes="error-label")

    def _has_templates(self) -> bool:
        """
        Vérifie si des templates sont disponibles pour ce plugin.
        
        Returns:
            bool: True si des templates existent
        """
        try:
            templates = self.template_manager.get_plugin_templates(self.source_id)
            return bool(templates)
        except Exception as e:
            logger.error(f"Erreur lors de la vérification des templates pour {self.source_id}: {e}")
            return False

    def _get_template_options(self) -> List[Tuple[str, str]]:
        """
        Récupère les options de templates pour le sélecteur.
        
        Returns:
            List[Tuple[str, str]]: Liste de tuples (value, label) pour le sélecteur
        """
        try:
            templates = self.template_manager.get_plugin_templates(self.source_id)
            options = [(template_id, template.get('name', template_id)) 
                      for template_id, template in templates.items()]
            
            # Ajouter une option vide en tête de liste
            return [("", "-- Sélectionner un template --")] + options
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des options de templates: {e}")
            return [("", "-- Erreur de chargement --")]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Gère les clics sur les boutons.
        
        Args:
            event: Événement de bouton pressé
        """
        try:
            button_id = event.button.id
            if button_id and button_id.startswith(f"apply_template_{self.source_id}"):
                logger.debug(f"Bouton d'application de template pressé pour {self.source_id}")
                self._apply_selected_template()
                
        except Exception as e:
            logger.error(f"Erreur lors du traitement du clic sur le bouton {event.button.id}: {e}")
            logger.error(traceback.format_exc())

    def on_select_changed(self, event: Select.Changed) -> None:
        """
        Gère les changements dans les listes déroulantes.
        
        Args:
            event: Événement de changement de sélection
        """
        try:
            select_id = event.select.id
            if select_id and select_id.startswith(f"template_{self.source_id}"):
                logger.debug(f"Sélection de template modifiée: {event.value}")
                # Option: appliquer automatiquement le template
                # self._apply_selected_template()
                
        except Exception as e:
            logger.error(f"Erreur lors du traitement du changement de sélection: {e}")
            logger.error(traceback.format_exc())

    def _apply_selected_template(self) -> None:
        """
        Applique le template sélectionné aux champs de configuration.
        """
        try:
            # Trouver le sélecteur de template
            template_select_id = f"template_{self.source_id}_{self.instance_id}"
            template_select = self.query_one(f"#" + template_select_id, Select)
            
            if not template_select or not template_select.value:
                logger.debug("Pas de template sélectionné")
                return
                
            template_id = template_select.value
            logger.debug(f"Application du template {template_id}")
            
            # Récupérer les variables du template
            variables = self.template_manager.get_template_variables(self.source_id, template_id)
            if variables:
                self.on_template_applied(template_id, variables)
            else:
                logger.warning(f"Pas de variables trouvées dans le template {template_id}")
                
        except Exception as e:
            logger.error(f"Erreur lors de l'application du template: {e}")
            logger.error(traceback.format_exc())

    def update_dependent_fields(self, source_field: Any) -> None:
        """
        Met à jour tous les champs qui dépendent d'un champ source.

        Args:
            source_field: Champ source dont les dépendants doivent être mis à jour
        """
        if self._is_updating_values:
            logger.debug("Mise à jour récursive évitée dans update_dependent_fields")
            return
            
        try:
            self._is_updating_values = True
            
            if not source_field or not hasattr(source_field, 'unique_id'):
                logger.warning("Tentative de mise à jour des dépendants d'un champ invalide")
                return

            source_id = source_field.unique_id
            logger.debug(f"Mise à jour des champs dépendants de {source_id}")

            # Vérifier si le champ source a des dépendants
            if source_id not in self._dependent_fields_map:
                logger.debug(f"Aucun champ dépendant trouvé pour {source_id}")
                return

            # Parcourir tous les champs dépendants
            for dependent_id in self._dependent_fields_map[source_id]:
                dependent_field = self.fields_by_id.get(dependent_id)
                if not dependent_field:
                    logger.warning(f"Champ dépendant {dependent_id} non trouvé")
                    continue

                try:
                    # 1. Mise à jour de l'état d'activation
                    if hasattr(dependent_field, 'enabled_if'):
                        self._update_field_enabled_state(dependent_field)

                    # 2. Mise à jour des options dynamiques
                    if hasattr(dependent_field, 'dynamic_options'):
                        self._update_field_dynamic_options(dependent_field)

                    # 3. Mise à jour de la valeur dépendante
                    if hasattr(dependent_field, 'depends_on'):
                        self._update_field_dependent_value(dependent_field)

                except Exception as e:
                    logger.error(f"Erreur lors de la mise à jour du champ dépendant {dependent_id}: {e}")
                    logger.error(traceback.format_exc())
                    
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour des champs dépendants: {e}")
            logger.error(traceback.format_exc())
        finally:
            self._is_updating_values = False

    def _analyze_plugin_dependencies(self, config_fields: List[Dict[str, Any]]) -> None:
        """
        Analyse les dépendances entre plugins.

        Args:
            config_fields: Liste des configurations de champs
        """
        try:
            self._plugin_dependencies = {}
            self._dependent_plugins_map = {}

            logger.debug(f"Analyse des dépendances entre plugins pour {len(config_fields)} champs")

            for field_config in config_fields:
                field_base_id = field_config.get('id')
                if not field_base_id:
                    continue

                # Construire l'ID unique du champ
                field_unique_id = self._get_unique_field_id(field_base_id)

                # Collecter les dépendances de plugins
                plugin_dependencies = set()

                # 1. Dépendance enabled_if
                if 'enabled_if' in field_config and 'field' in field_config['enabled_if']:
                    dep_field = field_config['enabled_if']['field']
                    if '.' in dep_field:
                        plugin_dependencies.add(dep_field.split('.')[0])

                # 2. Dépendance depends_on
                if 'depends_on' in field_config and '.' in field_config['depends_on']:
                    plugin_dependencies.add(field_config['depends_on'].split('.')[0])

                # 3. Dépendances dynamiques
                for dynamic_key in ['dynamic_options', 'dynamic_default']:
                    if dynamic_key in field_config and 'args' in field_config[dynamic_key]:
                        for arg in field_config[dynamic_key]['args']:
                            if 'field' in arg and '.' in arg['field']:
                                plugin_dependencies.add(arg['field'].split('.')[0])

                # Stocker les dépendances
                if plugin_dependencies:
                    self._plugin_dependencies[field_unique_id] = plugin_dependencies
                    logger.debug(f"Champ {field_unique_id} dépend des plugins: {plugin_dependencies}")

                    # Construire le mapping inverse
                    for dep_plugin in plugin_dependencies:
                        if dep_plugin not in self._dependent_plugins_map:
                            self._dependent_plugins_map[dep_plugin] = set()
                        self._dependent_plugins_map[dep_plugin].add(field_unique_id)
                        
            logger.debug(f"Analyse des dépendances entre plugins terminée: {len(self._plugin_dependencies)} champs avec dépendances de plugins")
                        
        except Exception as e:
            logger.error(f"Erreur lors de l'analyse des dépendances entre plugins: {e}")
            logger.error(traceback.format_exc())

    def update_plugin_dependencies(self, plugin_id: str, is_enabled: bool) -> None:
        """
        Met à jour les champs qui dépendent d'un plugin.

        Args:
            plugin_id: ID du plugin dont l'état a changé
            is_enabled: Nouvel état du plugin
        """
        if self._is_updating_values:
            return
            
        try:
            self._is_updating_values = True
            logger.debug(f"Mise à jour des dépendances pour le plugin {plugin_id} (enabled={is_enabled})")
            
            # Vérifier si des champs dépendent de ce plugin
            if plugin_id not in self._dependent_plugins_map:
                logger.debug(f"Aucun champ dépendant du plugin {plugin_id}")
                return
                
            # Parcourir tous les champs dépendants
            for field_id in self._dependent_plugins_map[plugin_id]:
                field = self.fields_by_id.get(field_id)
                if not field:
                    logger.warning(f"Champ dépendant {field_id} non trouvé")
                    continue
                    
                # Vérifier si le champ a une dépendance explicite avec ce plugin
                required_state = True  # Par défaut, on suppose que le champ nécessite que le plugin soit activé
                if hasattr(field, 'plugin_dependencies') and plugin_id in field.plugin_dependencies:
                    required_state = field.plugin_dependencies[plugin_id]
                    
                # Activer/désactiver le champ selon l'état du plugin
                should_enable = (is_enabled == required_state)
                logger.debug(f"Mise à jour de l'état du champ {field_id}: {should_enable}")
                self._toggle_field_state(field, should_enable)
                
                # Si le champ est désactivé, appliquer sa valeur par défaut
                if not should_enable and hasattr(field, 'field_config') and 'default' in field.field_config:
                    default_value = field.field_config['default']
                    self._apply_value_to_field(field, default_value)
                    
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour des dépendances du plugin {plugin_id}: {e}")
            logger.error(traceback.format_exc())
        finally:
            self._is_updating_values = False

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """
        Gère les changements d'état des cases à cocher.
        
        Args:
            event: Événement de changement de case à cocher
        """
        try:
            # Gestion spécifique au plugin
            checkbox_id = event.checkbox.id
            value = event.value
            logger.debug(f"Changement d'état de la case à cocher {checkbox_id} -> {value}")

            # Trouver le champ source
            source_field = None
            for field in self.fields_by_id.values():
                if isinstance(field, CheckboxField) and checkbox_id == f"checkbox_{field.source_id}_{field.field_id}":
                    source_field = field
                    break
                elif isinstance(field, CheckboxGroupField):
                    prefix = f"checkbox_group_{field.source_id}_{field.field_id}_"
                    if checkbox_id.startswith(prefix):
                        field.on_checkbox_changed(event)
                        source_field = field
                        break

            if source_field:
                logger.debug(f"Champ source identifié: {source_field.unique_id}")
                if isinstance(source_field, CheckboxField):
                    source_field.value = event.value
                    # Mettre à jour le widget
                    self._update_field_widget(source_field, event.value)
                self.update_dependent_fields(source_field)
            else:
                logger.warning(f"Champ source non trouvé pour checkbox {checkbox_id}")
                
        except Exception as e:
            logger.error(f"Erreur lors du traitement du changement d'état de la case à cocher: {e}")
            logger.error(traceback.format_exc())

    def on_template_applied(self, template_name: str, variables: Dict[str, Any]) -> None:
        """
        Gère l'application d'un template aux champs du plugin.
        
        Args:
            template_name: Nom du template appliqué
            variables: Variables du template à appliquer
        """
        try:
            logger.debug(f"Application du template '{template_name}' avec {len(variables)} variables")
            
            # Empêcher les mises à jour récursives
            if self._is_updating_values:
                logger.warning("Application de template ignorée pour éviter une récursion")
                return
                
            self._is_updating_values = True
            
            # Réinitialiser les structures de suivi
            self._applied_values = {}
            self._field_errors = {}
            self._pending_values = {}
            self._field_retry_counts = {}
            
            # Appliquer chaque variable du template
            for var_name, value in variables.items():
                field = self._find_field_for_variable(var_name)
                
                if field:
                    # Planifier l'application de la valeur
                    self._pending_values[field.field_id] = value
                    
                    # Démarrer avec un premier essai d'application
                    self._apply_value_to_field(field, value)
                else:
                    logger.warning(f"Aucun champ trouvé pour la variable '{var_name}' du template")
            
            # Gérer les valeurs en attente non appliquées
            if self._pending_values:
                logger.debug(f"Valeurs de template en attente: {len(self._pending_values)}")
                self.call_later(self._retry_pending_values, 0.1)
                
        except Exception as e:
            logger.error(f"Erreur lors de l'application du template: {e}")
            logger.error(traceback.format_exc())
        finally:
            self._is_updating_values = False

    def _find_field_for_variable(self, var_name: str) -> Optional[ConfigField]:
        """
        Recherche un champ correspondant à une variable du template.
        
        Args:
            var_name: Nom de la variable à rechercher
            
        Returns:
            Optional[ConfigField]: Champ correspondant ou None
        """
        try:
            # Rechercher par variable_name
            for field in self.fields_by_id.values():
                if hasattr(field, 'source_id') and field.source_id == self.source_id:
                    if hasattr(field, 'variable_name') and field.variable_name == var_name:
                        return field
                        
            # Rechercher par field_id
            for field in self.fields_by_id.values():
                if hasattr(field, 'source_id') and field.source_id == self.source_id:
                    if field.field_id == var_name:
                        return field
                        
            logger.warning(f"Aucun champ trouvé pour la variable {var_name}")
            return None
            
        except Exception as e:
            logger.error(f"Erreur lors de la recherche du champ pour la variable {var_name}: {e}")
            return None

    def _retry_pending_values(self) -> None:
        """
        Réessaie d'appliquer les valeurs en attente.
        """
        try:
            if not self._pending_values:
                return
                
            logger.debug(f"Tentative de réappliquer {len(self._pending_values)} valeurs en attente")
            
            # Créer une copie pour éviter les problèmes de modification pendant l'itération
            pending_copy = self._pending_values.copy()
            
            for field_id, value in pending_copy.items():
                # Trouver le champ
                field = None
                for f in self.fields_by_id.values():
                    if hasattr(f, 'field_id') and f.field_id == field_id:
                        field = f
                        break
                        
                if not field:
                    logger.warning(f"Champ {field_id} non trouvé pour la réapplication de valeur")
                    continue
                    
                # Réessayer d'appliquer la valeur
                success = self._apply_value_to_field(field, value)
                
                # Si succès, retirer de la liste d'attente
                if success:
                    self._pending_values.pop(field_id, None)
                    
            # Planifier une nouvelle tentative si nécessaire
            if self._pending_values:
                # Calculer le délai pour la prochaine tentative (exponentiel avec limite)
                max_retries = max(self._field_retry_counts.values()) if self._field_retry_counts else 0
                delay = min(2 ** max_retries * 0.1, 5.0)  # Maximum 5 secondes
                logger.debug(f"Planification d'une nouvelle tentative dans {delay}s pour {len(self._pending_values)} valeurs")
                self.call_later(self._retry_pending_values, delay)
                
        except Exception as e:
            logger.error(f"Erreur lors de la réapplication des valeurs en attente: {e}")
            logger.error(traceback.format_exc())

    def _apply_value_to_field(self, field: Any, value: Any) -> bool:
        """
        Applique une valeur à un champ avec gestion des tentatives.
        
        Args:
            field: Le champ cible
            value: La valeur à appliquer
            
        Returns:
            bool: True si l'application a réussi
        """
        if not field:
            return False
            
        try:
            field_id = getattr(field, 'field_id', str(field))
            
            # Initialiser le compteur de tentatives si nécessaire
            if field_id not in self._field_retry_counts:
                self._field_retry_counts[field_id] = 0
                
            # Si la valeur a déjà été appliquée avec succès
            if field_id in self._applied_values and self._applied_values[field_id] == value:
                return True
                
            # Utiliser la méthode dédiée du conteneur parent
            success = super()._apply_value_to_field(field, value)
            
            if success:
                # Marquer comme appliquée avec succès
                self._applied_values[field_id] = value
                # Réinitialiser le compteur de tentatives
                self._field_retry_counts[field_id] = 0
                return True
                
            # Gérer l'échec
            self._field_retry_counts[field_id] += 1
            
            # Abandonner après trop de tentatives
            if self._field_retry_counts[field_id] >= self._max_retry_attempts:
                logger.error(f"Abandon après {self._max_retry_attempts} tentatives pour le champ {field_id}")
                self._field_errors[field_id] = f"Échec après {self._max_retry_attempts} tentatives"
                self._pending_values.pop(field_id, None)
                return False
                
            logger.warning(f"Échec de l'application de la valeur pour {field_id} (tentative {self._field_retry_counts[field_id]})")
            return False
            
        except Exception as e:
            logger.error(f"Erreur lors de l'application de la valeur au champ {getattr(field, 'field_id', str(field))}: {e}")
            logger.error(traceback.format_exc())
            return False

    def collect_values(self) -> Dict[str, Any]:
        """
        Collecte toutes les valeurs actuelles des champs.
        
        Returns:
            Dict[str, Any]: Dictionnaire des valeurs {variable_name: value}
        """
        values = {}
        
        try:
            for field_id, field in self.fields_by_id.items():
                # Ne considérer que les champs de ce plugin
                if not hasattr(field, 'source_id') or field.source_id != self.source_id:
                    continue
                    
                # Ne pas inclure le champ de template
                if field_id == 'template':
                    continue
                    
                # Récupérer la valeur actuelle
                if hasattr(field, 'get_value'):
                    # Utiliser le nom de variable pour l'export
                    var_name = getattr(field, 'variable_name', field_id)
                    
                    try:
                        value = field.get_value()
                        
                        # Traitement spécial pour les checkbox_group
                        if (hasattr(field, 'field_config') and 
                            field.field_config.get('type') == 'checkbox_group'):
                            # Assurer que c'est une liste
                            if not value:
                                value = []
                            elif not isinstance(value, list):
                                value = [value]
                                
                        # Ajouter à la collection
                        values[var_name] = value
                        logger.debug(f"Valeur collectée pour {var_name}: {value}")
                        
                    except Exception as e:
                        logger.error(f"Erreur lors de la collecte de la valeur pour {var_name}: {e}")
            
        except Exception as e:
            logger.error(f"Erreur lors de la collecte des valeurs: {e}")
            logger.error(traceback.format_exc())
            
        return values

    def is_valid(self) -> bool:
        """
        Vérifie si tous les champs du conteneur sont valides.
        
        Returns:
            bool: True si tous les champs sont valides
        """
        try:
            for field_id, field in self.fields_by_id.items():
                # Ne considérer que les champs de ce plugin
                if not hasattr(field, 'source_id') or field.source_id != self.source_id:
                    continue
                    
                # Ignorer les champs désactivés
                if hasattr(field, 'disabled') and field.disabled:
                    continue
                    
                # Vérifier la validité du champ
                if hasattr(field, 'validate_input') and hasattr(field, 'get_value'):
                    value = field.get_value()
                    is_valid, error_msg = field.validate_input(value)
                    
                    if not is_valid:
                        logger.error(f"Validation échouée pour {field_id}: {error_msg}")
                        return False
            
            # Si tous les champs ont passé la validation
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de la validation des champs: {e}")
            logger.error(traceback.format_exc())
            return False

    def reset_to_defaults(self) -> None:
        """
        Réinitialise tous les champs à leurs valeurs par défaut.
        """
        if self._is_updating_values:
            logger.warning("Réinitialisation ignorée pour éviter une récursion")
            return
            
        try:
            self._is_updating_values = True
            logger.debug(f"Réinitialisation des champs à leurs valeurs par défaut")
            
            # Parcourir tous les champs de ce plugin
            for field_id, field in self.fields_by_id.items():
                if not hasattr(field, 'source_id') or field.source_id != self.source_id:
                    continue
                    
                # Récupérer la valeur par défaut si disponible
                if hasattr(field, 'field_config') and 'default' in field.field_config:
                    default_value = field.field_config['default']
                    
                    # Appliquer la valeur par défaut
                    self._apply_value_to_field(field, default_value)
                    logger.debug(f"Champ {field_id} réinitialisé à sa valeur par défaut: {default_value}")
                    
        except Exception as e:
            logger.error(f"Erreur lors de la réinitialisation des champs: {e}")
            logger.error(traceback.format_exc())
        finally:
            self._is_updating_values = False

    def apply_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """
        Applique un instantané de valeurs à tous les champs.
        Utile pour restaurer un état précédent ou appliquer une configuration complète.
        
        Args:
            snapshot: Dictionnaire des valeurs {variable_name: value}
        """
        if self._is_updating_values:
            logger.warning("Application de snapshot ignorée pour éviter une récursion")
            return
            
        try:
            self._is_updating_values = True
            logger.debug(f"Application d'un snapshot de {len(snapshot)} valeurs")
            
            # Réinitialiser les structures de suivi
            self._applied_values = {}
            self._field_errors = {}
            self._pending_values = {}
            self._field_retry_counts = {}
            
            # Appliquer chaque valeur du snapshot
            for var_name, value in snapshot.items():
                field = self._find_field_for_variable(var_name)
                
                if field:
                    # Planifier l'application de la valeur
                    self._pending_values[field.field_id] = value
                    
                    # Démarrer avec un premier essai d'application
                    self._apply_value_to_field(field, value)
                else:
                    logger.warning(f"Aucun champ trouvé pour la variable '{var_name}' du snapshot")
            
            # Gérer les valeurs en attente non appliquées
            if self._pending_values:
                logger.debug(f"Valeurs de snapshot en attente: {len(self._pending_values)}")
                self.call_later(self._retry_pending_values, 0.1)
                
        except Exception as e:
            logger.error(f"Erreur lors de l'application du snapshot: {e}")
            logger.error(traceback.format_exc())
        finally:
            self._is_updating_values = False

    def get_field_errors(self) -> Dict[str, str]:
        """
        Récupère les erreurs rencontrées lors de l'application des valeurs.
        
        Returns:
            Dict[str, str]: Dictionnaire des erreurs {field_id: error_message}
        """
        return self._field_errors.copy()
        
    def get_pending_values(self) -> Dict[str, Any]:
        """
        Récupère les valeurs en attente d'application.
        
        Returns:
            Dict[str, Any]: Dictionnaire des valeurs en attente {field_id: value}
        """
        return self._pending_values.copy()
        
    def get_applied_values(self) -> Dict[str, Any]:
        """
        Récupère les valeurs appliquées avec succès.
        
        Returns:
            Dict[str, Any]: Dictionnaire des valeurs appliquées {field_id: value}
        """
        return self._applied_values.copy()

    def call_later(self, callback: Callable, delay: float) -> None:
        """
        Planifie l'exécution différée d'une fonction.
        
        Args:
            callback: Fonction à exécuter
            delay: Délai en secondes
        """
        try:
            # Utiliser la méthode de l'application si disponible
            if hasattr(self, 'app') and hasattr(self.app, 'call_later'):
                self.app.call_later(callback, delay)
                return
                
            # Fallback pour les tests: exécution immédiate
            callback()
            
        except Exception as e:
            logger.error(f"Erreur lors de la planification d'un callback: {e}")
            logger.error(traceback.format_exc())
