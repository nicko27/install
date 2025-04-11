# ui/config_screen/config_field.py CORRIGÉ
from textual.app import ComposeResult
from textual.containers import HorizontalGroup, VerticalGroup
from textual.widgets import Label, Select, Input, Checkbox
import os
from typing import Dict, Any, Optional, Tuple, List, Set, Union, Callable
import importlib.util
import sys
import traceback
import re
from pathlib import Path

from ..utils.logging import get_logger

logger = get_logger('config_field')

class ConfigField(VerticalGroup):
    """
    Classe de base pour tous les champs de configuration.
    Gère les dépendances entre champs et les valeurs dynamiques.
    """

    def __init__(self, source_id: str, field_id: str, field_config: Dict[str, Any],
                fields_by_id: Optional[Dict[str, Any]] = None, is_global: bool = False):
        """
        Initialise un champ de configuration.

        Args:
            source_id: ID de la source (plugin ou config globale)
            field_id: ID du champ
            field_config: Configuration du champ
            fields_by_id: Dictionnaire des champs indexés par ID
            is_global: Indique si c'est un champ global
        """
        super().__init__()
        self.add_class("field-type-base")
        self.source_id = source_id
        self.field_id = field_id
        self.field_config = field_config or {}
        self.fields_by_id = fields_by_id or {}
        self.is_global = is_global
        self.disabled = False

        # Attributs importants qui doivent être initialisés
        self.unique_id = None
        self.enabled_if = None
        self.depends_on = None
        self.variable_name = None
        self._field_retry_counts = {}
        self._max_retry_attempts = 3
        self.plugin_dependencies = {}
        
        # Initialiser l'ID unique
        self._initialize_unique_id()

        # Initialiser les dépendances
        self._initialize_dependencies()

        # Initialiser la valeur par défaut
        self.value = self._get_default_value()
        logger.debug(f"Champ {self.unique_id} initialisé avec valeur: {self.value}")

    def _initialize_unique_id(self) -> None:
        """
        Initialise l'ID unique du champ.
        Cet ID sera utilisé pour identifier le champ dans les dépendances.
        """
        if 'unique_id' in self.field_config:
            self.unique_id = self.field_config['unique_id']
            logger.debug(f"Unique ID trouvé dans la configuration: {self.unique_id}")
        elif not self.is_global and '_' in self.source_id:
            try:
                *name_parts, instance_part = self.source_id.split('_')
                instance_id = int(instance_part)
                self.unique_id = f"{self.field_id}_{instance_id}"
                logger.debug(f"Unique ID généré à partir du source_id: {self.unique_id}")
            except ValueError:
                self.unique_id = self.field_id
                logger.warning(f"Impossible d'extraire l'instance_id de {self.source_id}, utilisation de field_id comme unique_id")
        else:
            self.unique_id = self.field_id
            logger.debug(f"Unique ID = field_id: {self.unique_id}")

    def _initialize_dependencies(self) -> None:
        """
        Initialise les dépendances du champ.
        Trois types de dépendances sont gérés:
        1. enabled_if: pour l'activation conditionnelle
        2. depends_on: pour les valeurs dépendantes
        3. plugin_dependencies: pour les dépendances aux plugins
        """
        # Dépendance d'activation
        self.enabled_if = self.field_config.get('enabled_if')
        if self.enabled_if:
            logger.debug(f"Champ {self.unique_id} a une dépendance d'activation: {self.enabled_if}")
            self._original_default = self.field_config.get('default')
        
        # Dépendance de valeur
        self.depends_on = self.field_config.get('depends_on')
        if self.depends_on:
            logger.debug(f"Champ {self.unique_id} dépend de {self.depends_on} pour sa valeur")

        # Nom de la variable pour l'export
        self.variable_name = self.field_config.get('variable', self.field_id)

        # Dépendances de plugins
        self._initialize_plugin_dependencies()

    def _initialize_plugin_dependencies(self) -> None:
        """
        Initialise les dépendances aux plugins.
        Analyse la configuration pour trouver les relations avec d'autres plugins.
        """
        self.plugin_dependencies = {}
        
        # Si le champ a une dépendance à un autre plugin via enabled_if
        if self.enabled_if and 'field' in self.enabled_if and '.' in self.enabled_if['field']:
            plugin_id = self.enabled_if['field'].split('.')[0]
            self.plugin_dependencies[plugin_id] = True  # Nécessite que le plugin soit activé
            logger.debug(f"Dépendance à l'activation du plugin {plugin_id} détectée pour {self.unique_id}")
        
        # Si le champ a une dépendance à un autre plugin via depends_on
        if self.depends_on and '.' in self.depends_on:
            plugin_id = self.depends_on.split('.')[0]
            self.plugin_dependencies[plugin_id] = True  # Nécessite que le plugin soit activé
            logger.debug(f"Dépendance à la valeur du plugin {plugin_id} détectée pour {self.unique_id}")

    def _get_default_value(self) -> Any:
        """
        Détermine la valeur par défaut du champ en fonction des dépendances et configurations.

        Returns:
            Any: Valeur par défaut déterminée
        """
        # 1. Vérifier si le champ est désactivé
        if self.enabled_if and not self._check_enabled_condition():
            logger.debug(f"Champ {self.unique_id} désactivé, utilisation de la valeur par défaut originale")
            return self._original_default if hasattr(self, '_original_default') else self.field_config.get('default')

        # 2. Vérifier les dépendances de valeur
        if self.depends_on and 'values' in self.field_config:
            dependent_value = self._get_dependent_value()
            if dependent_value is not None:
                logger.debug(f"Valeur dépendante pour {self.unique_id}: {dependent_value}")
                return dependent_value

        # 3. Vérifier les valeurs dynamiques
        if 'dynamic_default' in self.field_config:
            dynamic_value = self._get_dynamic_default()
            if dynamic_value is not None:
                logger.debug(f"Valeur dynamique pour {self.unique_id}: {dynamic_value}")
                return dynamic_value

        # 4. Valeur par défaut statique
        default_value = self.field_config.get('default')
        logger.debug(f"Valeur par défaut statique pour {self.unique_id}: {default_value}")
        return default_value

    def _check_enabled_condition(self) -> bool:
        """
        Vérifie si la condition d'activation est satisfaite.
        
        Returns:
            bool: True si le champ doit être activé, False sinon
        """
        if not self.enabled_if:
            return True

        dep_field_id = self.enabled_if.get('field')
        required_value = self.enabled_if.get('value')
        
        if not dep_field_id:
            logger.warning(f"Condition enabled_if sans field pour {self.unique_id}")
            return True

        # Obtenir le champ dépendant
        dep_field = self._get_field_by_id(dep_field_id)
        if not dep_field:
            logger.warning(f"Champ dépendant '{dep_field_id}' non trouvé pour {self.unique_id}")
            return False

        # Récupérer et normaliser les valeurs
        dep_value = self._get_field_value(dep_field)
        dep_value_norm = self._normalize_bool_value(dep_value)
        required_value_norm = self._normalize_bool_value(required_value)

        result = dep_value_norm == required_value_norm
        logger.debug(f"Vérification condition d'activation pour {self.unique_id}: {dep_value} == {required_value} => {result}")
        return result

    def _normalize_bool_value(self, value: Any) -> bool:
        """
        Normalise une valeur en booléen pour les comparaisons cohérentes.

        Args:
            value: Valeur à normaliser

        Returns:
            bool: Valeur normalisée
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', 't', 'yes', 'y', '1')
        try:
            return bool(int(value))
        except (ValueError, TypeError):
            pass
        return bool(value)

    def _get_dependent_value(self) -> Any:
        """
        Récupère la valeur en fonction d'un autre champ.

        Returns:
            Any: Valeur basée sur le champ dépendant ou None si non trouvée
        """
        if not self.depends_on:
            return None

        # Obtenir le champ dépendant
        dep_field = self._get_field_by_id(self.depends_on)
        if not dep_field:
            logger.warning(f"Champ dépendant '{self.depends_on}' non trouvé pour {self.unique_id}")
            return None

        # Récupérer la valeur du champ dépendant
        dependent_value = self._get_field_value(dep_field)
        values_map = self.field_config.get('values', {})

        # Vérifier si la valeur existe dans le mapping
        if dependent_value in values_map:
            logger.debug(f"Valeur pour {self.unique_id} basée sur {self.depends_on}={dependent_value}: {values_map[dependent_value]}")
            return values_map[dependent_value]
        
        logger.debug(f"Valeur {dependent_value} du champ {self.depends_on} non trouvée dans le mapping 'values'")
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
            logger.debug(f"Chargement de valeur dynamique pour {self.unique_id} via script: {script_name}")

            # Déterminer le chemin du script
            script_path = self._resolve_script_path(dynamic_config)
            if not script_path or not os.path.exists(script_path):
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
            function_args, function_kwargs = self._prepare_function_args(dynamic_config)

            # Appeler la fonction
            result = getattr(module, function_name)(*function_args, **function_kwargs)
            logger.debug(f"Résultat obtenu du script pour {self.unique_id}: {result}")

            # Traiter le résultat
            return self._process_dynamic_result(result, dynamic_config)

        except Exception as e:
            logger.error(f"Erreur lors de l'obtention de la valeur dynamique pour {self.unique_id}: {e}")
            logger.error(traceback.format_exc())
            return None

    def _prepare_function_args(self, dynamic_config: Dict[str, Any]) -> Tuple[List[Any], Dict[str, Any]]:
        """
        Prépare les arguments pour une fonction dynamique.

        Args:
            dynamic_config: Configuration pour la valeur dynamique

        Returns:
            Tuple[List[Any], Dict[str, Any]]: Arguments positionnels et nommés
        """
        args_list = []
        kwargs_dict = {}
        current_instance_id = self._get_instance_id_from_unique_id()

        if 'args' not in dynamic_config:
            return args_list, kwargs_dict

        for arg_config in dynamic_config['args']:
            param_name = arg_config.get('param_name')
            value = None
            found = False

            # Argument provenant d'un autre champ
            if 'field' in arg_config:
                field_id = arg_config['field']
                field = self._get_field_by_id(field_id)

                if field:
                    value = self._get_field_value(field)
                    found = True
                    logger.debug(f"Argument dynamique: Récupération de '{field_id}' -> {value}")
                else:
                    logger.warning(f"Argument dynamique: Champ source '{field_id}' non trouvé.")

            # Argument avec valeur directe
            elif 'value' in arg_config:
                value = arg_config['value']
                found = True
                logger.debug(f"Argument dynamique: Utilisation de la valeur statique '{value}'")

            # Ajouter l'argument
            if found:
                if param_name:
                    kwargs_dict[param_name] = value
                else:
                    args_list.append(value)

        logger.debug(f"Arguments préparés pour fonction dynamique: args={args_list}, kwargs={kwargs_dict}")
        return args_list, kwargs_dict

    def _process_dynamic_result(self, result: Any, dynamic_config: Dict[str, Any]) -> Any:
        """
        Traite le résultat d'une fonction dynamique.

        Args:
            result: Résultat retourné par la fonction
            dynamic_config: Configuration pour la valeur dynamique

        Returns:
            Any: Valeur extraite du résultat
        """
        if result is None:
            return None

        # Cas 1: Résultat au format (success, value)
        if isinstance(result, tuple) and len(result) == 2:
            success, value = result
            if not success:
                logger.warning(f"Fonction dynamique a échoué: {value}")
                return None
            if isinstance(value, dict) and 'value_key' in dynamic_config:
                return value.get(dynamic_config['value_key'])
            return value

        # Cas 2: Résultat est un dictionnaire
        if isinstance(result, dict):
            if 'value_key' in dynamic_config:
                return result.get(dynamic_config['value_key'])
            logger.warning("Résultat dynamique est un dict mais 'value_key' n'est pas défini.")
            return None

        # Cas 3: Tout autre type de résultat
        return result

    def _get_instance_id_from_unique_id(self) -> Optional[int]:
        """
        Extrait l'ID d'instance de l'unique_id.

        Returns:
            Optional[int]: ID d'instance ou None si non trouvé
        """
        if self.is_global:
            return None
        match = re.search(r'_(\d+)$', self.unique_id)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
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
            if path.startswith('@[') and path.endswith(']'):
                dir_name = path[2:-1]
                base_dir = Path(__file__).parent.parent.parent
                return str(base_dir / dir_name / script_name)
            if not os.path.isabs(path):
                plugin_dir = Path(__file__).parent.parent.parent / 'plugins' / self.source_id
                return str(plugin_dir / path / script_name)
            return str(Path(path) / script_name)

        # Cas 2: Script global
        if dynamic_config.get('global', False):
            base_dir = Path(__file__).parent.parent.parent
            return str(base_dir / 'scripts' / script_name)

        # Cas 3: Script dans le dossier du plugin (défaut)
        base_dir = Path(__file__).parent.parent.parent
        return str(base_dir / 'plugins' / self.source_id / script_name)

    def _import_script_module(self, script_path: str) -> Optional[Any]:
        """
        Importe un module Python depuis un chemin de fichier.

        Args:
            script_path: Chemin vers le script à importer

        Returns:
            Optional[Any]: Module importé ou None en cas d'échec
        """
        try:
            script_dir = os.path.dirname(script_path)
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)

            module_name = f"dynamic_module_{os.path.basename(script_path).replace('.py', '')}_{hash(script_path)}"
            spec = importlib.util.spec_from_file_location(module_name, script_path)
            if not spec:
                logger.error(f"Impossible de créer un spécificateur pour {script_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return module

        except Exception as e:
            logger.error(f"Erreur lors de l'importation du module {script_path}: {e}")
            logger.error(traceback.format_exc())
            return None

    def _notify_dependencies(self) -> None:
        """
        Notifie les champs dépendants d'un changement de valeur.
        Utilise le conteneur parent pour la gestion des dépendances.
        """
        try:
            # Méthode 1: Utiliser le conteneur parent direct
            parent = self._get_parent_container()
            
            if parent and hasattr(parent, 'update_dependent_fields'):
                logger.debug(f"Notification des dépendances depuis {self.unique_id} via conteneur parent")
                parent.update_dependent_fields(self)
                return
                
            # Méthode 2: Remonter la hiérarchie pour trouver le premier conteneur capable
            logger.debug(f"Recherche du conteneur parent pour {self.unique_id}")
            current_parent = self.parent
            while current_parent:
                if hasattr(current_parent, 'update_dependent_fields'):
                    logger.debug(f"Conteneur parent trouvé: {type(current_parent).__name__}")
                    current_parent.update_dependent_fields(self)
                    return
                current_parent = current_parent.parent
                
            logger.warning(f"Aucun conteneur parent capable de gérer les dépendances trouvé pour {self.unique_id}")
            
        except Exception as e:
            logger.error(f"Erreur lors de la notification des dépendances pour {self.unique_id}: {e}")
            logger.error(traceback.format_exc())

    def get_value(self) -> Any:
        """
        Récupère la valeur actuelle du champ.

        Returns:
            Any: Valeur du champ
        """
        return getattr(self, 'value', None)

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
        try:
            logger.debug(f"set_value appelée pour {self.unique_id} avec valeur {value}")
            old_value = getattr(self, 'value', None)
            
            # Mettre à jour la valeur interne
            self.value = value
            
            # Mettre à jour le widget si demandé
            if update_input:
                self._update_field_widget(self, value)
            
            # Notifier les dépendances si demandé
            if update_dependencies and old_value != value:
                self._notify_dependencies()
                
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de la définition de la valeur pour {self.unique_id}: {e}")
            logger.error(traceback.format_exc())
            return False

    def validate_input(self, value: Any) -> Tuple[bool, str]:
        """
        Valide une valeur d'entrée.

        Args:
            value: Valeur à valider

        Returns:
            Tuple[bool, str]: (validité, message d'erreur)
        """
        if self.field_config.get('required', False) and (value is None or str(value).strip() == ""):
            return False, "Ce champ est requis."
        return True, ""

    def compose(self) -> ComposeResult:
        """
        Compose l'interface du champ de configuration.

        Returns:
            ComposeResult: Résultat de la composition
        """
        label = self.field_config.get('label', self.field_id)

        # Création de l'en-tête avec le libellé
        with HorizontalGroup(classes="field-header", id=f"header_{self.unique_id}"):
            if self.field_config.get('required', False):
                yield Label(label, classes="field-label")
                yield Label(" *", classes="required-field")
            else:
                yield Label(label, classes="field-label")

        # Description du champ
        description = self.field_config.get('description')
        if description:
            yield Label(description, classes="field-description")

        # Vérifier si le champ doit être activé ou non selon les dépendances
        self._check_initial_state()

    def on_mount(self) -> None:
        """
        Méthode appelée lors du montage du champ.
        Permet d'initialiser des comportements après le montage.
        """
        # Configuration des dépendances après le montage
        if hasattr(self, 'dynamic_options'):
            self.update_dynamic_options()

    def on_select_changed(self, event: Select.Changed) -> None:
        """
        Gère les changements de valeur pour les champs de type select.
        Doit être implémenté dans SelectField.
        
        Args:
            event: Événement de changement du select
        """
        pass  # Méthode à surcharger dans les classes dérivées

    def _update_field_widget(self, field: Any, value: Any) -> None:
        """
        Met à jour le widget d'un champ avec une nouvelle valeur.

        Args:
            field: Le champ à mettre à jour
            value: La nouvelle valeur à appliquer
        """
        if field is None:
            logger.warning("Tentative de mise à jour d'un widget d'un champ None")
            return
            
        try:
            field_id = getattr(field, 'unique_id', getattr(field, 'field_id', 'unknown'))
            field_type = getattr(field, 'field_type', 'unknown')
            logger.debug(f"Mise à jour du widget pour {field_id} (type: {field_type}) avec valeur: {value}")
            
            # Normaliser la valeur selon le type de champ
            if field_type == 'checkbox':
                value = self._normalize_bool_value(value)
            elif field_type == 'ip':
                if value is not None and not isinstance(value, str):
                    value = str(value)
            elif field_type == 'checkbox_group':
                if not isinstance(value, dict):
                    value = {}
                    
            # Mettre à jour le widget selon son type
            if hasattr(field, 'input') and field.input:
                if value is not None:
                    field.input.value = str(value)
                    logger.debug(f"Valeur du widget input mise à jour: {value}")
            elif hasattr(field, 'select') and field.select:
                if value is not None:
                    field.select.value = str(value)
                    logger.debug(f"Valeur du widget select mise à jour: {value}")
            elif hasattr(field, 'checkbox') and field.checkbox:
                field.checkbox.value = bool(value)
                logger.debug(f"Valeur du widget checkbox mise à jour: {value}")
            elif hasattr(field, 'checkboxes') and isinstance(field.checkboxes, dict):
                for checkbox_id, checkbox in field.checkboxes.items():
                    if checkbox and value and isinstance(value, dict):
                        checkbox.value = bool(value.get(checkbox_id, False))
                        logger.debug(f"Valeur du widget checkbox_group[{checkbox_id}] mise à jour: {value.get(checkbox_id, False)}")
                    
            logger.debug(f"Widget mis à jour avec succès pour {field_id}")
            
        except Exception as e:
            field_id = getattr(field, 'unique_id', str(field))
            logger.error(f"Erreur lors de la mise à jour du widget pour {field_id}: {str(e)}")
            logger.error(traceback.format_exc())

    def _apply_value_to_field(self, value: Any) -> bool:
        """
        Applique une valeur à ce champ en gérant les erreurs et les retries.

        Args:
            value: La valeur à appliquer

        Returns:
            bool: True si la valeur a été appliquée avec succès
        """
        try:
            field_id = self.unique_id
            field_type = getattr(self, 'field_type', 'unknown')
            logger.debug(f"Application de la valeur {value} au champ {field_id} (type: {field_type})")

            # Vérifier le nombre de tentatives
            if field_id not in self._field_retry_counts:
                self._field_retry_counts[field_id] = 0
                
            # Normaliser la valeur selon le type de champ
            normalized_value = value
            if field_type == 'checkbox':
                normalized_value = self._normalize_bool_value(value)
            elif field_type == 'ip' and value is not None:
                if not isinstance(value, str):
                    normalized_value = str(value)
            elif field_type == 'checkbox_group':
                if not isinstance(value, dict):
                    normalized_value = {}

            # Appliquer la valeur
            success = self.set_value(normalized_value, update_dependencies=False)
            
            # Réinitialiser le compteur de tentatives en cas de succès
            if success:
                self._field_retry_counts[field_id] = 0
                logger.debug(f"Valeur appliquée avec succès au champ {field_id}")
                return True

            # Gérer les échecs
            self._field_retry_counts[field_id] += 1
            if self._field_retry_counts[field_id] >= self._max_retry_attempts:
                logger.error(f"Échec après {self._field_retry_counts[field_id]} tentatives pour le champ {field_id}")
                self._field_retry_counts[field_id] = 0
                return False

            logger.warning(f"Tentative {self._field_retry_counts[field_id]} échouée pour le champ {field_id}")
            return False

        except Exception as e:
            logger.error(f"Erreur lors de l'application de la valeur au champ {self.unique_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def _check_initial_state(self) -> None:
        """
        Vérifie et applique l'état initial du champ en fonction de ses dépendances.
        Gère à la fois les dépendances de plugins et les dépendances de champs.
        """
        try:
            # Vérifier les dépendances de plugin
            if self.plugin_dependencies:
                for plugin_id, required_state in self.plugin_dependencies.items():
                    plugin_container = self._get_plugin_container(plugin_id)
                    if not plugin_container:
                        logger.warning(f"Plugin container non trouvé pour {plugin_id}")
                        continue
                        
                    plugin_enabled = getattr(plugin_container, 'is_enabled', True)
                    if plugin_enabled != required_state:
                        logger.debug(f"Plugin {plugin_id} est {plugin_enabled}, requis {required_state} - désactivation du champ {self.unique_id}")
                        self._toggle_field_state(False)
                        return
                        
            # Vérifier les dépendances de champ via enabled_if
            if self.enabled_if:
                should_enable = self._check_enabled_condition()
                logger.debug(f"Vérification d'état initial pour {self.unique_id} via enabled_if: {should_enable}")
                self._toggle_field_state(should_enable)
                
            # Obtenir une valeur dépendante si nécessaire
            if self.depends_on and 'values' in self.field_config:
                dependent_value = self._get_dependent_value()
                if dependent_value is not None:
                    logger.debug(f"Application de la valeur dépendante initiale pour {self.unique_id}: {dependent_value}")
                    self.value = dependent_value
                    self._update_field_widget(self, dependent_value)
                    
        except Exception as e:
            logger.error(f"Erreur lors de la vérification de l'état initial pour {self.unique_id}: {str(e)}")
            logger.error(traceback.format_exc())
            self._toggle_field_state(False)  # Désactiver par sécurité en cas d'erreur

    def update_dynamic_options(self) -> None:
        """
        Met à jour les options dynamiques du champ.
        Cette méthode est destinée à être surchargée par les classes filles (SelectField, CheckboxGroupField).
        """
        pass # Ne fait rien dans la classe de base

    def _get_field_value(self, field: Any) -> Any:
        """
        Récupère la valeur d'un champ de manière sécurisée.

        Args:
            field: Champ dont on veut la valeur

        Returns:
            Any: Valeur du champ ou None si non trouvée
        """
        try:
            if field is None:
                logger.warning("Tentative de récupération de valeur d'un champ None")
                return None
                
            # Utiliser get_value si disponible
            if hasattr(field, 'get_value'):
                return field.get_value()
                
            # Fallback sur l'attribut value
            return getattr(field, 'value', None)
            
        except Exception as e:
            field_id = getattr(field, 'unique_id', str(field))
            logger.error(f"Erreur lors de la récupération de la valeur pour {field_id}: {e}")
            logger.error(traceback.format_exc())
            return None

    def _get_config_screen(self) -> Optional[Any]:
        """
        Récupère l'écran de configuration parent.
        
        Returns:
            Optional[Any]: L'écran de configuration ou None si non trouvé
        """
        try:
            # Vérifier que l'application existe
            if not hasattr(self, 'app') or not self.app:
                logger.warning("Application non trouvée")
                return None

            # Vérifier que l'écran existe
            if not hasattr(self.app, 'screen') or not self.app.screen:
                logger.warning("Écran non trouvé")
                return None

            # Vérifier que c'est bien un écran de configuration
            from .config_screen import PluginConfig
            if not isinstance(self.app.screen, PluginConfig):
                logger.warning(f"Écran trouvé n'est pas un PluginConfig: {type(self.app.screen)}")
                return None

            return self.app.screen

        except Exception as e:
            logger.error(f"Erreur lors de la récupération de l'écran de configuration: {e}")
            logger.error(traceback.format_exc())
            return None

    def _get_plugin_container(self, plugin_id: str) -> Optional[Any]:
        """
        Récupère le conteneur de configuration d'un plugin.
        
        Args:
            plugin_id: L'identifiant du plugin

        Returns:
            Optional[Any]: Le conteneur de configuration du plugin ou None si non trouvé
        """
        try:
            screen = self._get_config_screen()
            if not screen:
                return None
                
            return screen.get_plugin_container(plugin_id)
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du conteneur pour {plugin_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def _get_field_by_id(self, field_id: str) -> Optional[Any]:
        """
        Récupère un champ par son ID.

        Args:
            field_id: ID du champ à récupérer

        Returns:
            Optional[Any]: Le champ trouvé ou None
        """
        try:
            # Cas 1: ID qualifié avec un plugin (format: plugin.field)
            if '.' in field_id:
                plugin_id, field_name = field_id.split('.')
                plugin_container = self._get_plugin_container(plugin_id)
                
                if plugin_container and hasattr(plugin_container, 'fields_by_id'):
                    # Créer l'ID unique si nécessaire
                    instance_id = self._get_instance_id_from_unique_id()
                    unique_field_id = f"{field_name}_{instance_id}" if instance_id is not None else field_name
                    
                    # Chercher dans le plugin
                    if unique_field_id in plugin_container.fields_by_id:
                        return plugin_container.fields_by_id[unique_field_id]
                    
                    # Fallback: chercher par field_id simple
                    if field_name in plugin_container.fields_by_id:
                        return plugin_container.fields_by_id[field_name]
                    
                logger.warning(f"Champ {field_id} non trouvé dans le plugin {plugin_id}")
                return None
            
            # Cas 2: Vérifier dans notre dictionnaire local
            if self.fields_by_id and field_id in self.fields_by_id:
                return self.fields_by_id[field_id]
            
            # Cas 3: Vérifier avec l'ID unique potentiel
            instance_id = self._get_instance_id_from_unique_id()
            unique_field_id = f"{field_id}_{instance_id}" if instance_id is not None else field_id
            
            if self.fields_by_id and unique_field_id in self.fields_by_id:
                return self.fields_by_id[unique_field_id]
            
            # Cas 4: Chercher dans le conteneur parent
            from .config_container import ConfigContainer
            parent = self._get_parent_container()
            
            if parent and hasattr(parent, 'fields_by_id'):
                if field_id in parent.fields_by_id:
                    return parent.fields_by_id[field_id]
                if unique_field_id in parent.fields_by_id:
                    return parent.fields_by_id[unique_field_id]
            
            logger.warning(f"Champ {field_id} non trouvé")
            return None

        except Exception as e:
            logger.error(f"Erreur lors de la récupération du champ {field_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def _get_parent_container(self) -> Optional[Any]:
        """
        Récupère le conteneur parent de ce champ.
        
        Returns:
            Optional[Any]: Le conteneur parent ou None
        """
        try:
            from .config_container import ConfigContainer
            parent = next((p for p in self.ancestors if isinstance(p, ConfigContainer)), None)
            return parent
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du conteneur parent pour {self.unique_id}: {e}")
            return None

    def _toggle_field_state(self, enable: bool) -> None:
        """
        Active ou désactive le champ.

        Args:
            enable: True pour activer, False pour désactiver
        """
        try:
            old_state = not self.disabled
            self.disabled = not enable
            
            # Mettre à jour les classes CSS
            if enable:
                self.remove_class('disabled')
            else:
                self.add_class('disabled')

            # Désactiver aussi les widgets internes
            self._toggle_internal_widgets(enable)
            
            logger.debug(f"État du champ {self.unique_id} modifié: {old_state} -> {enable}")

            # Si le champ est désactivé, appliquer sa valeur par défaut
            if not enable and hasattr(self, 'field_config') and 'default' in self.field_config:
                default_value = self.field_config.get('default')
                logger.debug(f"Application de la valeur par défaut pour {self.unique_id}: {default_value}")
                self.set_value(default_value, update_dependencies=False)

        except Exception as e:
            logger.error(f"Erreur lors de la modification de l'état du champ {self.unique_id}: {str(e)}")
            logger.error(traceback.format_exc())

    def _toggle_internal_widgets(self, enable: bool) -> None:
        """
        Active ou désactive les widgets internes du champ.

        Args:
            enable: True pour activer, False pour désactiver
        """
        try:
            widgets_to_toggle = []
            
            # Collecter tous les widgets du champ
            if hasattr(self, 'input'):
                widgets_to_toggle.append(self.input)
            if hasattr(self, 'select'):
                widgets_to_toggle.append(self.select)
            if hasattr(self, 'checkbox'):
                widgets_to_toggle.append(self.checkbox)
            if hasattr(self, 'checkboxes') and isinstance(self.checkboxes, dict):
                widgets_to_toggle.extend(self.checkboxes.values())
            if hasattr(self, '_browse_button') and self._browse_button:
                widgets_to_toggle.append(self._browse_button)

            # Mettre à jour chaque widget
            for widget in widgets_to_toggle:
                if widget:
                    widget.disabled = not enable
                    if enable:
                        widget.remove_class('disabled')
                    else:
                        widget.add_class('disabled')
                    logger.debug(f"État du widget {widget.id if hasattr(widget, 'id') else 'sans ID'} modifié: disabled={not enable}")

        except Exception as e:
            logger.error(f"Erreur lors de la modification de l'état des widgets internes pour {self.unique_id}: {str(e)}")
            logger.error(traceback.format_exc())