from textual.app import ComposeResult
from textual.containers import VerticalGroup, HorizontalGroup
from textual.widgets import Label, Input, Select, Button, Checkbox
from textual.reactive import reactive
from textual.widget import Widget
from typing import Dict, List, Any, Optional, Set, Type

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
    """
    Conteneur de base pour les champs de configuration.
    
    Gère à la fois les configurations de plugins et les configurations globales,
    avec les dépendances entre champs.
    """
    
    # Définition des attributs réactifs
    source_id = reactive("")       # Identifiant de la source (plugin ou config globale)
    title = reactive("")           # Titre d'affichage
    icon = reactive("")            # Icône d'affichage
    description = reactive("")     # Description du conteneur
    is_global = reactive(False)    # Si True, c'est une configuration globale

    # Mapping des types de champs
    FIELD_TYPES = {
        'text': TextField,
        'directory': DirectoryField,
        'ip': IPField,
        'checkbox': CheckboxField,
        'select': SelectField,
        'checkbox_group': CheckboxGroupField,
        'password': PasswordField
    }

    def __init__(self, source_id: str, title: str, icon: str, description: str,
                 fields_by_id: Dict[str, Any], config_fields: List[Dict[str, Any]], 
                 is_global: bool = False, **kwargs):
        """
        Initialise un conteneur de configuration.
        
        Args:
            source_id: Identifiant de la source (plugin ou config globale)
            title: Titre d'affichage
            icon: Icône d'affichage
            description: Description du conteneur
            fields_by_id: Dictionnaire des champs par ID
            config_fields: Liste des configurations de champs
            is_global: Si True, c'est une configuration globale
            **kwargs: Arguments supplémentaires pour le VerticalGroup
        """
        # Ajouter la classe CSS du conteneur
        if "classes" in kwargs:
            if "config-container" not in kwargs["classes"]:
                kwargs["classes"] += " config-container"
        else:
            kwargs["classes"] = "config-container"

        super().__init__(**kwargs)
        
        # Définir les attributs réactifs
        self.source_id = source_id
        self.title = title
        self.icon = icon
        self.description = description
        self.is_global = is_global
        
        # Attributs non réactifs
        self.fields_by_id = fields_by_id
        self.config_fields = config_fields
        
        # État interne
        self._updating_dependencies = False  # Flag pour éviter les cycles
        self._field_dependencies = {}  # Mapping des dépendances entre champs
        self._fields_to_remove = set()  # Champs à supprimer lors de la prochaine mise à jour

    def compose(self) -> ComposeResult:
        """
        Compose le conteneur avec ses champs de configuration.
        
        Returns:
            ComposeResult: Résultat de la composition
        """
        # En-tête: titre et description
        with VerticalGroup(classes="config-header"):
            yield Label(f"{self.icon} {self.title}", classes="config-title")
            if self.description:
                yield Label(self.description, classes="config-description")

        # Si aucun champ, afficher un message
        if not self.config_fields:
            with VerticalGroup(classes="no-config"):
                with HorizontalGroup(classes="no-config-content"):
                    yield Label("ℹ️", classes="no-config-icon")
                    yield Label(f"Rien à configurer pour ce plugin", classes="no-config-label")
                return

        # Créer les champs de configuration
        with VerticalGroup(classes="config-fields"):
            # Préparer l'analyse des dépendances
            self._analyze_field_dependencies(self.config_fields)
            
            # Création des champs
            for field_config in self.config_fields:
                field = self._create_field(field_config)
                if field:
                    yield field

    def _analyze_field_dependencies(self, config_fields: List[Dict[str, Any]]) -> None:
        """
        Analyse les dépendances entre les champs pour optimiser les mises à jour.
        
        Args:
            config_fields: Liste des configurations de champs
        """
        self._field_dependencies = {}
        
        # Parcourir tous les champs
        for field_config in config_fields:
            field_id = field_config.get('id')
            if not field_id:
                continue
            
            # Collecter tous les types de dépendances
            dependencies = []
            
            # 1. Dépendance enabled_if (ce champ dépend d'un autre pour son activation)
            if 'enabled_if' in field_config and 'field' in field_config['enabled_if']:
                dependencies.append(field_config['enabled_if']['field'])
            
            # 2. Dépendance depends_on (ce champ dépend d'un autre pour sa valeur)
            if 'depends_on' in field_config:
                dependencies.append(field_config['depends_on'])
            
            # 3. Dépendance dynamic_options (ce champ dépend d'autres pour ses options)
            if 'dynamic_options' in field_config and 'args' in field_config['dynamic_options']:
                for arg in field_config['dynamic_options']['args']:
                    if 'field' in arg:
                        dependencies.append(arg['field'])
            
            # Ajouter les dépendances au dictionnaire
            for dep_field in dependencies:
                if dep_field:
                    if dep_field not in self._field_dependencies:
                        self._field_dependencies[dep_field] = set()
                    self._field_dependencies[dep_field].add(field_id)
                    logger.debug(f"Dépendance identifiée: {field_id} dépend de {dep_field}")
        
        logger.debug(f"Analyse des dépendances terminée: {self._field_dependencies}")

    def _create_field(self, field_config: Dict[str, Any]) -> Optional[Widget]:
        """
        Crée un champ de configuration à partir de sa configuration.
        
        Args:
            field_config: Configuration du champ
            
        Returns:
            Optional[Widget]: Champ créé ou None en cas d'erreur
        """
        field_id = field_config.get('id')
        if not field_id:
            logger.warning(f"Champ sans ID dans {self.source_id}")
            return None
            
        field_type = field_config.get('type', 'text')
        logger.debug(f"Création du champ {field_id} de type {field_type}")
        
        # Déterminer la classe du champ
        field_class = self.FIELD_TYPES.get(field_type, TextField)

        try:
            # Créer le champ avec accès aux autres champs
            field = field_class(
                self.source_id, 
                field_id, 
                field_config, 
                self.fields_by_id, 
                is_global=self.is_global
            )
            
            # Enregistrer le champ dans le dictionnaire
            self.fields_by_id[field_id] = field
            
            # Si c'est un champ de type checkbox, ajouter un gestionnaire d'événements
            if field_type in ['checkbox', 'checkbox_group']:
                field.on_checkbox_changed = self.on_checkbox_changed
                
            return field
            
        except Exception as e:
            logger.error(f"Erreur lors de la création du champ {field_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """
        Gère les changements d'état des cases à cocher.
        
        Args:
            event: Événement de changement de la case à cocher
        """
        # Extraire l'ID de la case à cocher
        checkbox_id = event.checkbox.id
        logger.debug(f"Checkbox changée: {checkbox_id} -> {event.value}")

        # Trouver le champ correspondant
        for field_id, field in self.fields_by_id.items():
            if isinstance(field, CheckboxField) and checkbox_id == f"checkbox_{field.source_id}_{field.field_id}":
                logger.debug(f"Case à cocher trouvée: {field.field_id}")
                
                # Mettre à jour la valeur du champ
                field.value = event.value
                
                # Mettre à jour les champs dépendants
                self.update_dependent_fields(field)
                break

    def update_dependent_fields(self, source_field: Widget) -> None:
        """
        Met à jour les champs qui dépendent d'un champ spécifique.
        
        Args:
            source_field: Champ source dont la valeur a changé
        """
        # Protection contre les appels récursifs
        if self._updating_dependencies:
            logger.debug(f"Mise à jour des dépendances déjà en cours, ignorer l'appel pour {source_field.field_id}")
            return
            
        try:
            # Marquer le début de la mise à jour
            self._updating_dependencies = True
            
            # Réinitialiser la liste des champs à supprimer
            self._fields_to_remove = set()
            
            # Trouver les champs dépendants directs
            source_id = getattr(source_field, 'field_id', None)
            if not source_id or source_id not in self._field_dependencies:
                logger.debug(f"Aucune dépendance trouvée pour {source_id}")
                return
                
            dependent_ids = self._field_dependencies[source_id]
            logger.debug(f"Mise à jour des champs dépendant de {source_id}: {dependent_ids}")
            
            # Parcourir les champs dépendants
            for dependent_id in dependent_ids:
                if dependent_id not in self.fields_by_id:
                    continue
                    
                dependent_field = self.fields_by_id[dependent_id]
                
                # Mettre à jour tous les aspects du champ dépendant
                self._update_dependent_field(dependent_field, source_field)
            
            # Supprimer les champs invalidés après la mise à jour
            self._process_fields_to_remove()
            
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour des dépendances: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
        finally:
            # Toujours réinitialiser le flag
            self._updating_dependencies = False

    def _update_dependent_field(self, dependent_field: Widget, source_field: Widget) -> None:
        """
        Met à jour tous les aspects d'un champ dépendant.
        
        Args:
            dependent_field: Champ dépendant à mettre à jour
            source_field: Champ source dont la valeur a changé
        """
        # 1. TRAITEMENT DES CONDITIONS ENABLED_IF
        self._update_field_enabled_state(dependent_field, source_field)
        
        # 2. TRAITEMENT DES OPTIONS DYNAMIQUES
        self._update_field_dynamic_options(dependent_field, source_field)
        
        # 3. TRAITEMENT DES VALEURS DÉPENDANTES
        self._update_field_dependent_value(dependent_field, source_field)

    def _update_field_enabled_state(self, dependent_field: Widget, source_field: Widget) -> None:
        """
        Met à jour l'état d'activation d'un champ selon ses dépendances.
        
        Args:
            dependent_field: Champ dépendant à mettre à jour
            source_field: Champ source dont la valeur a changé
        """
        # Vérifier si le champ a une condition d'activation
        if not hasattr(dependent_field, 'enabled_if') or not dependent_field.enabled_if:
            return
            
        # Vérifier si la dépendance concerne le champ source
        if dependent_field.enabled_if.get('field') != source_field.field_id:
            return
            
        source_value = self._get_field_value(source_field)
        required_value = dependent_field.enabled_if.get('value')
        
        # Normaliser les valeurs booléennes si nécessaire
        source_value = self._normalize_boolean_value(source_value)
        required_value = self._normalize_boolean_value(required_value)
        
        # Déterminer si le champ doit être activé
        should_enable = source_value == required_value
        
        if not should_enable:
            logger.debug(f"Désactivation du champ {dependent_field.field_id}")
            dependent_field.disabled = True
            dependent_field.add_class('disabled')
            
            # Si le champ doit aussi être retiré, l'ajouter à la liste
            self._fields_to_remove.add(dependent_field.field_id)
        else:
            logger.debug(f"Activation du champ {dependent_field.field_id}")
            dependent_field.disabled = False
            dependent_field.remove_class('disabled')
            
            # Restaurer l'état du widget si disponible
            self._restore_field_state(dependent_field)

    def _get_field_value(self, field: Widget) -> Any:
        """
        Récupère la valeur d'un champ de manière sécurisée.
        
        Args:
            field: Champ dont il faut récupérer la valeur
            
        Returns:
            Any: Valeur du champ
        """
        if hasattr(field, 'get_value'):
            return field.get_value()
        elif hasattr(field, 'value'):
            return field.value
        return None
    
    def _normalize_boolean_value(self, value: Any) -> Any:
        """
        Normalise une valeur booléenne.
        
        Args:
            value: Valeur à normaliser
            
        Returns:
            Any: Valeur normalisée
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', 't', 'yes', 'y', '1')
        return bool(value)

    def _update_field_dynamic_options(self, dependent_field: Widget, source_field: Widget) -> None:
        """
        Met à jour les options dynamiques d'un champ.
        
        Args:
            dependent_field: Champ dépendant à mettre à jour
            source_field: Champ source dont la valeur a changé
        """
        # Vérifier si le champ a besoin de mettre à jour ses options dynamiques
        if hasattr(dependent_field, 'update_dynamic_options'):
            logger.debug(f"Mise à jour des options dynamiques pour {dependent_field.field_id}")
            dependent_field.update_dynamic_options()
            
            # Vérifier si le champ est un GroupCheckboxField et n'a plus d'options
            if (hasattr(dependent_field, 'options') and 
                hasattr(dependent_field, 'field_config') and
                dependent_field.field_config.get('type') == 'checkbox_group'):
                
                options_empty = (not dependent_field.options or len(dependent_field.options) == 0)
                
                if options_empty:
                    logger.debug(f"Le champ {dependent_field.field_id} n'a plus d'options, planifié pour suppression")
                    self._fields_to_remove.add(dependent_field.field_id)

    def _update_field_dependent_value(self, dependent_field: Widget, source_field: Widget) -> None:
        """
        Met à jour la valeur d'un champ qui dépend d'un autre.
        
        Args:
            dependent_field: Champ dépendant à mettre à jour
            source_field: Champ source dont la valeur a changé
        """
        # Vérifier si le champ dépend explicitement de la source pour sa valeur
        depends_on = getattr(dependent_field, 'depends_on', None)
        
        if depends_on == source_field.field_id:
            logger.debug(f"Mise à jour de la valeur de {dependent_field.field_id} qui dépend de {source_field.field_id}")
            
            # Récupérer la nouvelle valeur dynamique
            if hasattr(dependent_field, '_get_default_value'):
                new_value = dependent_field._get_default_value()
                logger.debug(f"Nouvelle valeur dynamique pour {dependent_field.field_id}: {new_value}")
                
                # Appliquer la nouvelle valeur
                if hasattr(dependent_field, 'set_value'):
                    dependent_field.set_value(new_value)
                else:
                    dependent_field.value = new_value

    def _process_fields_to_remove(self) -> None:
        """
        Traite les champs à supprimer après une mise à jour des dépendances.
        """
        if not self._fields_to_remove:
            return
            
        logger.debug(f"Traitement des champs à supprimer: {self._fields_to_remove}")
        
        # Supprimer les champs du dictionnaire et de l'interface
        for field_id in self._fields_to_remove:
            if field_id in self.fields_by_id:
                field = self.fields_by_id[field_id]
                
                # Supprimer du dictionnaire
                del self.fields_by_id[field_id]
                
                # Supprimer de l'interface
                if field in self.children:
                    field.remove()
                    
                logger.debug(f"Champ {field_id} supprimé")

    def _restore_field_state(self, field: Widget) -> bool:
        """
        Restaure l'état d'un champ qui était désactivé.
        
        Args:
            field: Champ à restaurer
            
        Returns:
            bool: True si la restauration a réussi
        """
        logger.debug(f"Restauration de l'état du champ {field.field_id}")
        
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
                    logger.debug(f"Restauration de la valeur pour {field.field_id}: {field._saved_value}")
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
        logger.warning(f"Aucun widget interactif trouvé pour {field.field_id}")
        return False