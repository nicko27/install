from textual.app import ComposeResult
from textual.containers import HorizontalGroup, VerticalGroup
from textual.widgets import Label, Select
import os
from typing import Dict, Any, Optional, Tuple, List
import importlib.util
import sys
import traceback

from ..utils.logging import get_logger

logger = get_logger('config_field')

class ConfigField(VerticalGroup):
    """
    Classe de base pour tous les champs de configuration.
    
    Cette classe fournit les fonctionnalités communes à tous les champs
    et doit être sous-classée par des types de champs spécifiques.
    """
    
    def __init__(self, source_id: str, field_id: str, field_config: Dict[str, Any], 
                fields_by_id: Optional[Dict[str, Any]] = None, is_global: bool = False):
        """
        Initialise un champ de configuration.
        
        Args:
            source_id: ID de la source (plugin ou config globale)
            field_id: ID du champ
            field_config: Configuration du champ
            fields_by_id: Dictionnaire des champs indexés par ID (pour les dépendances)
            is_global: Indique si c'est un champ global ou spécifique à un plugin
        """
        super().__init__()
        self.source_id = source_id         # ID de la source (plugin ou config globale)
        self.field_id = field_id           # ID du champ
        
        # Utiliser l'ID unique s'il est disponible
        self.unique_id = field_config.get('unique_id', field_id)
        logger.debug(f"Initialisation du champ {field_id} avec unique_id: {self.unique_id}")
        
        self.field_config = field_config   # Configuration du champ
        self.fields_by_id = fields_by_id or {}  # Champs indexés par ID pour les dépendances
        self.is_global = is_global         # Indique si c'est un champ global ou plugin

        # Attributs pour la gestion des dépendances
        self.enabled_if = field_config.get('enabled_if')
        self._original_default = field_config.get('default') if self.enabled_if else None
        
        # Pour le suivi de l'état d'initialisation
        self._initialization_complete = False
        self._pending_disabled_state = None
            
        # Nom de la variable pour l'export (peut être différent de l'ID)
        self.variable_name = field_config.get('variable', field_id)
        
        # Gestion des dépendances pour les valeurs dynamiques
        self.depends_on = field_config.get('depends_on')
        if self.depends_on:
            logger.debug(f"Champ {self.field_id} dépend de {self.depends_on}")

        # Initialisation de la valeur par défaut
        self.value = self._get_default_value()
        logger.debug(f"Champ {self.field_id} initialisé avec valeur: {self.value}")
        
        # Ne pas définir l'état disabled directement à l'initialisation
        # Cela sera fait plus tard avec _check_initial_enabled_state
        # qui est appelé après que tous les champs sont disponibles

    def _get_default_value(self) -> Any:
        """
        Détermine la valeur par défaut du champ.
        
        Returns:
            Any: Valeur par défaut du champ
        """
        # Cas 1: Dépendance sur un autre champ avec mapping de valeurs
        if self.depends_on and 'values' in self.field_config:
            return self._get_dependent_value()
            
        # Cas 2: Valeur par défaut dynamique via script
        if 'dynamic_default' in self.field_config:
            dynamic_value = self._get_dynamic_default()
            if dynamic_value is not None:
                return dynamic_value
                
        # Cas 3: Valeur par défaut statique dans la configuration
        if 'default' in self.field_config:
            return self.field_config.get('default')
            
        # Cas 4: Aucune valeur par défaut spécifiée
        return None

    def _get_dependent_value(self) -> Any:
        """
        Récupère la valeur en fonction d'un autre champ.
        
        Returns:
            Any: Valeur basée sur le champ dont dépend celui-ci
        """
        depends_on = self.depends_on
        if depends_on in self.fields_by_id:
            dependent_field = self.fields_by_id[depends_on]
            dependent_value = dependent_field.get_value()
            values_map = self.field_config['values']
            
            if dependent_value in values_map:
                logger.debug(f"Valeur pour {self.field_id} basée sur {depends_on}={dependent_value}: {values_map[dependent_value]}")
                return values_map[dependent_value]
                
        # Si pas de correspondance, utiliser la valeur par défaut standard
        return self.field_config.get('default')

    def _get_dynamic_default(self) -> Any:
        """
        Récupère une valeur par défaut dynamique via un script.
        
        Returns:
            Any: Valeur obtenue dynamiquement ou None en cas d'échec
        """
        try:
            if 'dynamic_default' not in self.field_config or 'script' not in self.field_config['dynamic_default']:
                return None
                
            dynamic_config = self.field_config['dynamic_default']
            script_name = dynamic_config['script']
            logger.debug(f"Chargement de valeur dynamique pour {self.field_id} via script: {script_name}")
            
            # Déterminer le chemin du script
            script_path = self._resolve_script_path(dynamic_config)
            if not os.path.exists(script_path):
                logger.error(f"Script non trouvé: {script_path}")
                return None
                
            # Importer le script
            module = self._import_script_module(script_path)
            if not module:
                return None
                
            # Déterminer la fonction à appeler
            function_name = dynamic_config.get('function', 'get_default_value')
            if not hasattr(module, function_name):
                logger.error(f"Fonction {function_name} non trouvée dans {script_name}")
                return None
                
            # Préparer les arguments
            function_args = self._prepare_function_args(dynamic_config)
            
            # Appeler la fonction
            result = getattr(module, function_name)(**function_args)
            logger.debug(f"Résultat obtenu du script: {result}")
            
            # Traiter le résultat
            return self._process_dynamic_result(result, dynamic_config)
            
        except Exception as e:
            logger.error(f"Erreur lors de l'obtention de la valeur dynamique: {e}")
            logger.error(traceback.format_exc())
            return None

    def _resolve_script_path(self, dynamic_config: Dict[str, Any]) -> str:
        """
        Résout le chemin d'un script dynamique.
        
        Args:
            dynamic_config: Configuration pour la valeur dynamique
            
        Returns:
            str: Chemin complet vers le script
        """
        script_name = dynamic_config['script']
        
        # Cas 1: Chemin personnalisé spécifié
        if 'path' in dynamic_config:
            path = dynamic_config['path']
            
            # Syntaxe @[directory]
            if path.startswith('@[') and path.endswith(']'):
                dir_name = path[2:-1]  # Extraire le nom du répertoire entre @[ et ]
                if dir_name == 'scripts':
                    return os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', script_name)
                return os.path.join(os.path.dirname(__file__), '..', '..', dir_name, script_name)
                
            # Chemin absolu ou relatif directement spécifié
            return os.path.join(path, script_name) if not os.path.isabs(path) else os.path.join(path, script_name)
            
        # Cas 2: Script global
        if dynamic_config.get('global', False):
            return os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', script_name)
            
        # Cas 3: Script dans le dossier du plugin
        return os.path.join(os.path.dirname(__file__), '..', '..', 'plugins', self.source_id, script_name)

    def _import_script_module(self, script_path: str) -> Optional[Any]:
        """
        Importe un module Python depuis un chemin de fichier.
        
        Args:
            script_path: Chemin vers le script à importer
            
        Returns:
            Optional[Any]: Module importé ou None en cas d'échec
        """
        try:
            # Ajouter le dossier du script au chemin de recherche
            script_dir = os.path.dirname(script_path)
            if script_dir not in sys.path:
                sys.path.append(script_dir)
            
            # Créer un spécificateur de module
            spec = importlib.util.spec_from_file_location("dynamic_module", script_path)
            if not spec:
                logger.error(f"Impossible de créer un spécificateur pour {script_path}")
                return None
                
            # Charger le module
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            return module
            
        except Exception as e:
            logger.error(f"Erreur lors de l'importation du module {script_path}: {e}")
            return None

    def _prepare_function_args(self, dynamic_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prépare les arguments à passer à la fonction dynamique.
        
        Args:
            dynamic_config: Configuration pour la valeur dynamique
            
        Returns:
            Dict[str, Any]: Arguments à passer à la fonction
        """
        args = {}
        
        if 'args' not in dynamic_config:
            return args
            
        for arg_config in dynamic_config['args']:
            # Argument provenant d'un autre champ
            if 'field' in arg_config:
                field_id = arg_config['field']
                if field_id in self.fields_by_id:
                    field_value = self.fields_by_id[field_id].get_value()
                    param_name = arg_config.get('param_name', field_id)
                    args[param_name] = field_value
                    
            # Argument avec valeur directe
            elif 'value' in arg_config:
                param_name = arg_config.get('param_name')
                if param_name:
                    args[param_name] = arg_config['value']
                    
        return args

    def _process_dynamic_result(self, result: Any, dynamic_config: Dict[str, Any]) -> Any:
        """
        Traite le résultat d'une fonction dynamique.
        
        Args:
            result: Résultat retourné par la fonction
            dynamic_config: Configuration pour la valeur dynamique
            
        Returns:
            Any: Valeur extraite du résultat
        """
        # Cas 1: Résultat au format (success, value)
        if isinstance(result, tuple) and len(result) == 2:
            success, value = result
            
            if not success:
                logger.warning(f"Fonction dynamique a échoué: {value}")
                return None
                
            # Extraire la valeur du dictionnaire si nécessaire
            if isinstance(value, dict):
                value_key = dynamic_config.get('value')
                if value_key and value_key in value:
                    return value[value_key]
                elif value:
                    return next(iter(value.values()))
            
            return value
            
        # Cas 2: Résultat est un dictionnaire
        if isinstance(result, dict):
            value_key = dynamic_config.get('value')
            if value_key and value_key in result:
                return result[value_key]
            elif result:
                return next(iter(result.values()))
                
        # Cas 3: Tout autre type de résultat
        return result

    def compose(self) -> ComposeResult:
        """
        Compose l'interface du champ de configuration.
        
        Returns:
            ComposeResult: Résultat de la composition
        """
        label = self.field_config.get('label', self.field_id)

        # Création de l'en-tête avec le libellé
        with HorizontalGroup(classes="field-header", id=f"header_{self.field_id}"):
            if self.field_config.get('required', False):
                yield Label(label, classes="field-label")
                yield Label(" *", classes="required-field")
            else:
                yield Label(label, classes="field-label")

    def on_mount(self) -> None:
        """
        Méthode appelée lorsque le widget est monté dans l'interface.
        """
        # Indiquer que l'initialisation est terminée
        self._initialization_complete = True
        
        # Appliquer l'état disabled en attente s'il y en a un
        if self._pending_disabled_state is not None:
            # Si le champ a une méthode set_disabled, l'utiliser
            if hasattr(self, 'set_disabled') and callable(self.set_disabled):
                logger.debug(f"Application de l'état disabled en attente: {self._pending_disabled_state} pour {self.field_id}")
                self.set_disabled(self._pending_disabled_state)
            # Sinon, appliquer directement les attributs
            else:
                logger.debug(f"Application directe de l'état disabled en attente: {self._pending_disabled_state} pour {self.field_id}")
                self.disabled = self._pending_disabled_state
                if self._pending_disabled_state:
                    self.add_class('disabled')
                else:
                    self.remove_class('disabled')
                    
            # Réinitialiser la valeur en attente
            self._pending_disabled_state = None
            
        # Vérifier les dépendances maintenant que tous les champs devraient être créés
        self._check_enabled_state()

    def _check_enabled_state(self) -> None:
        """
        Vérifie si le champ doit être activé ou désactivé selon ses dépendances.
        Cette version améliorée fait une recherche plus robuste des champs dépendants.
        """
        # Ignorer si pas de condition d'activation
        if not hasattr(self, 'enabled_if') or not self.enabled_if:
            logger.debug(f"Pas de condition enabled_if pour {self.field_id}")
            return
            
        dep_field_id = self.enabled_if.get('field')
        required_value = self.enabled_if.get('value')
        logger.debug(f"Vérification état pour {self.field_id}: dépend de {dep_field_id} avec valeur requise {required_value}")
        
        # Recherche améliorée du champ dépendant
        dep_field = self._find_dependent_field(dep_field_id)
        
        # Si le champ dépendant n'est pas trouvé, ne pas changer l'état actuel
        # C'est le changement principal : ne pas désactiver par défaut
        if not dep_field:
            logger.debug(f"Champ dépendant {dep_field_id} non trouvé pour {self.field_id}, état inchangé")
            return
            
        # Récupérer la valeur actuelle du champ dépendant
        current_value = self._get_field_value(dep_field)
        logger.debug(f"Valeur actuelle de {dep_field_id}: {current_value}")
        
        # Normaliser les valeurs pour la comparaison
        norm_current = self._normalize_bool_value(current_value)
        norm_required = self._normalize_bool_value(required_value)
        logger.debug(f"Après normalisation: {norm_current} == {norm_required}")
        
        # Déterminer si le champ doit être activé
        should_enable = norm_current == norm_required
        logger.debug(f"Le champ {self.field_id} doit être {'' if should_enable else 'dés'}activé")
        
        # Appliquer l'état d'activation
        self._set_enabled_state(should_enable)

    def _find_dependent_field(self, dep_field_id: str) -> Optional[Any]:
        """
        Recherche un champ dépendant de manière robuste.
        
        Args:
            dep_field_id: ID du champ dépendant à rechercher
            
        Returns:
            Optional[Any]: Champ trouvé ou None
        """
        # 1. Recherche directe par ID
        if dep_field_id in self.fields_by_id:
            logger.debug(f"Champ dépendant trouvé directement: {dep_field_id}")
            return self.fields_by_id[dep_field_id]
            
        # 2. Recherche par ID unique (avec suffixe numérique)
        for field_id, field in self.fields_by_id.items():
            if field_id.startswith(f"{dep_field_id}_") and field_id[len(dep_field_id)+1:].isdigit():
                logger.debug(f"Champ dépendant trouvé par ID unique: {field_id}")
                return field
                
        # 3. Recherche par attributs
        for field_id, field in self.fields_by_id.items():
            if hasattr(field, 'field_id') and field.field_id == dep_field_id:
                if hasattr(field, 'source_id') and field.source_id == self.source_id:
                    logger.debug(f"Champ dépendant trouvé par attributs: {field_id}")
                    return field
                    
        # 4. Recherche par ID préfixé (source_id.field_id)
        prefixed_id = f"{self.source_id}.{dep_field_id}"
        if prefixed_id in self.fields_by_id:
            logger.debug(f"Champ dépendant trouvé par ID préfixé: {prefixed_id}")
            return self.fields_by_id[prefixed_id]
            
        # Aucune correspondance trouvée
        logger.debug(f"Champ dépendant non trouvé: {dep_field_id}")
        return None

    def _get_field_value(self, field: Any) -> Any:
        """
        Récupère la valeur d'un champ de manière robuste.
        
        Args:
            field: Champ dont il faut récupérer la valeur
            
        Returns:
            Any: Valeur du champ
        """
        # Méthode 1: Utiliser get_value (standard)
        if hasattr(field, 'get_value') and callable(field.get_value):
            return field.get_value()
            
        # Méthode 2: Accéder directement à value
        if hasattr(field, 'value'):
            return field.value
            
        # Méthode 3: Pour CheckboxField, accéder à la checkbox
        if hasattr(field, 'checkbox') and hasattr(field.checkbox, 'value'):
            return field.checkbox.value
            
        # Méthode 4: Accéder à _internal_value (pour TextField)
        if hasattr(field, '_internal_value'):
            return field._internal_value
            
        logger.warning(f"Impossible de récupérer la valeur du champ {getattr(field, 'field_id', 'inconnu')}")
        return None

    def _normalize_bool_value(self, value: Any) -> Any:
        """
        Normalise une valeur en booléen si nécessaire.
        
        Args:
            value: Valeur à normaliser
            
        Returns:
            Any: Valeur normalisée
        """
        # Si c'est déjà un booléen, le laisser tel quel
        if isinstance(value, bool):
            return value
            
        # Si c'est une chaîne qui représente un booléen
        if isinstance(value, str):
            if value.lower() in ('true', 't', 'yes', 'y', '1'):
                return True
            elif value.lower() in ('false', 'f', 'no', 'n', '0'):
                return False
                
        # Pour d'autres types, tenter une conversion standard
        try:
            return bool(value)
        except:
            return value

    def _set_enabled_state(self, enabled: bool) -> None:
        """
        Active ou désactive le champ.
        
        Args:
            enabled: True pour activer, False pour désactiver
        """
        # Si l'initialisation n'est pas terminée, stocker l'état pour plus tard
        if not self._initialization_complete:
            self._pending_disabled_state = not enabled
            logger.debug(f"État d'activation stocké pour plus tard: enabled={enabled} pour {self.field_id}")
            return
            
        # Si le champ a une méthode set_disabled, l'utiliser
        if hasattr(self, 'set_disabled') and callable(self.set_disabled):
            logger.debug(f"Utilisation de set_disabled({not enabled}) pour {self.field_id}")
            self.set_disabled(not enabled)
        else:
            # Sinon, appliquer directement les attributs
            logger.debug(f"Application directe de disabled={not enabled} pour {self.field_id}")
            self.disabled = not enabled
            if not enabled:
                self.add_class('disabled')
            else:
                self.remove_class('disabled')

    def on_select_changed(self, event: Select.Changed) -> None:
        """
        Gère les changements de valeur pour les champs de type select.
        
        Args:
            event: Événement de changement du select
        """
        if not hasattr(self, 'field_id') or not event.select.id.endswith(self.field_id):
            return
            
        # Mettre à jour la valeur
        self.value = str(event.value) if event.value is not None else ""
        logger.debug(f"Valeur de {self.field_id} changée à {self.value}")

        # Mettre à jour les champs qui dépendent de celui-ci
        self._notify_dependent_fields()
    
    def _notify_dependent_fields(self):
        """Notifie les champs dépendants d'un changement de valeur"""
        if self.fields_by_id:
            for field_id, field in self.fields_by_id.items():
                if hasattr(field, 'depends_on') and field.depends_on == self.field_id:
                    field.value = field._get_default_value()
                    logger.debug(f"Mise à jour de {field_id} après changement de {self.field_id}")
                    
                    # Mettre à jour le widget si disponible
                    if hasattr(field, 'input'):
                        field.input.value = str(field.value) if field.value is not None else ""
                    elif hasattr(field, 'select'):
                        field.select.value = field.value

    def get_value(self) -> Any:
        """
        Récupère la valeur actuelle du champ.
        
        Returns:
            Any: Valeur du champ
        """
        return self.value
        
    def set_value(self, value: Any, update_input: bool = True, update_dependencies: bool = True) -> bool:
        """
        Définit la valeur du champ.
        
        Args:
            value: Nouvelle valeur
            update_input: Si True, met à jour le widget d'entrée
            update_dependencies: Si True, notifie les champs dépendants
            
        Returns:
            bool: True si la mise à jour a réussi
        """
        # À implémenter par les sous-classes
        self.value = value
        return True

    def update_dynamic_options(self) -> None:
        """
        Met à jour les options dynamiques du champ.
        Cette méthode est destinée à être surchargée par les classes filles.
        """
        pass

    def validate_input(self, value: Any) -> Tuple[bool, str]:
        """
        Valide une valeur d'entrée.
        
        Args:
            value: Valeur à valider
            
        Returns:
            Tuple[bool, str]: (validité, message d'erreur)
        """
        return True, ""