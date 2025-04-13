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
        
        # Transformer les noms de champs dans enabled_if pour tenir compte du contexte
        if self.enabled_if and 'field' in self.enabled_if:
            # Stocker l'ID simple pour référence
            self.enabled_if['simple_field'] = self.enabled_if['field']
            
            # Si le champ a un ID unique, essayer de construire un ID dépendant avec le même préfixe
            if '_' in self.unique_id and '_' not in self.enabled_if['field']:
                # Extraire le préfixe du plugin à partir de l'ID unique
                parts = self.unique_id.split('_')
                if len(parts) > 1:  # Au moins un underscore
                    plugin_prefix = '_'.join(parts[:-1])  # Tout sauf le dernier élément
                    # Construire un ID dépendant avec le même préfixe
                    potential_dep_field = f"{plugin_prefix}_{self.enabled_if['field']}"
                    logger.debug(f"Transformation de enabled_if: {self.enabled_if['field']} -> {potential_dep_field}")
                    self.enabled_if['transformed_field'] = potential_dep_field
            
        # Nom de la variable pour l'export (peut être différent de l'ID)
        self.variable_name = field_config.get('variable', field_id)
        
        # Gestion des dépendances pour les valeurs dynamiques
        self.depends_on = field_config.get('depends_on')
        
        # Transformer les noms de champs dans depends_on pour tenir compte du contexte
        if self.depends_on:
            # Stocker l'ID simple pour référence
            self.depends_on_simple = self.depends_on
            
            # Si le champ a un ID unique, essayer de construire un ID dépendant avec le même préfixe
            if '_' in self.unique_id and '_' not in self.depends_on:
                # Extraire le préfixe du plugin à partir de l'ID unique
                parts = self.unique_id.split('_')
                if len(parts) > 1:  # Au moins un underscore
                    plugin_prefix = '_'.join(parts[:-1])  # Tout sauf le dernier élément
                    # Construire un ID dépendant avec le même préfixe
                    potential_dep_field = f"{plugin_prefix}_{self.depends_on}"
                    logger.debug(f"Transformation de depends_on: {self.depends_on} -> {potential_dep_field}")
                    self.depends_on_transformed = potential_dep_field
            
            logger.debug(f"Champ {self.field_id} dépend de {self.depends_on}")
            
        # Transformer les noms de champs dans dynamic_options pour tenir compte du contexte
        if 'dynamic_options' in field_config and 'args' in field_config['dynamic_options']:
            self.dynamic_options = field_config['dynamic_options']
            self.dynamic_options_args_transformed = []
            
            for arg in self.dynamic_options['args']:
                if 'field' in arg:
                    # Stocker l'ID simple pour référence
                    arg['simple_field'] = arg['field']
                    
                    # Si le champ a un ID unique, essayer de construire un ID dépendant avec le même préfixe
                    if '_' in self.unique_id and '_' not in arg['field']:
                        # Extraire le préfixe du plugin à partir de l'ID unique
                        parts = self.unique_id.split('_')
                        if len(parts) > 1:  # Au moins un underscore
                            plugin_prefix = '_'.join(parts[:-1])  # Tout sauf le dernier élément
                            # Construire un ID dépendant avec le même préfixe
                            potential_dep_field = f"{plugin_prefix}_{arg['field']}"
                            logger.debug(f"Transformation de dynamic_options.arg.field: {arg['field']} -> {potential_dep_field}")
                            arg['transformed_field'] = potential_dep_field
                    
                    self.dynamic_options_args_transformed.append(arg)

        # Initialisation de la valeur par défaut
        self.value = self._get_default_value()
        logger.debug(f"Champ {self.field_id} initialisé avec valeur: {self.value}")

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

        # Vérifier si le champ doit être activé ou non selon les dépendances
        self._check_initial_enabled_state()

    def _check_initial_enabled_state(self) -> None:
        """
        Vérifie si le champ doit être initialement activé ou désactivé selon ses dépendances.
        """
        if not self.enabled_if:
            return
            
        # Chercher le champ dépendant par son ID
        dep_field_id = self.enabled_if['field']
        dep_field = None
        
        # Chercher tous les champs dont le field_id se termine par le nom du champ dépendant
        matching_fields = []
        suffix = f"{dep_field_id}_"
        
        for field_id, field in self.fields_by_id.items():
            field_id_attr = getattr(field, 'field_id', '')
            
            # Cas 1: Correspondance exacte
            if field_id_attr == dep_field_id:
                matching_fields.append(field)
                logger.debug(f"Correspondance exacte trouvée pour {dep_field_id}: {field_id}")
            
            # Cas 2: Le field_id se termine par _{dep_field_id}
            elif field_id_attr.startswith(suffix):
                matching_fields.append(field)
                logger.debug(f"Correspondance par suffixe trouvée pour {dep_field_id}: {field_id}")
        
        # S'il y a plusieurs correspondances, essayer de filtrer par le même plugin
        if len(matching_fields) > 1:
            same_plugin_fields = [f for f in matching_fields if getattr(f, 'source_id', '') == self.source_id]
            if same_plugin_fields:
                matching_fields = same_plugin_fields
                logger.debug(f"Filtré {len(same_plugin_fields)} champs du même plugin {self.source_id}")
        
        # Prendre le premier champ correspondant s'il y en a
        if matching_fields:
            dep_field = matching_fields[0]
            logger.debug(f"Champ dépendant sélectionné: {dep_field.field_id} (sur {len(matching_fields)} correspondances)")
                    
        logger.debug(f"Vérification état initial pour {self.field_id}: enabled_if={self.enabled_if}, "
                   f"champ dépendant trouvé: {dep_field is not None}")

        # Vérifier si le champ dépendant existe
        if dep_field:
            # Récupérer les valeurs pour la comparaison
            field_value = dep_field.value
            required_value = self.enabled_if.get('value')

            # Convertir en booléens si nécessaire pour la comparaison
            if isinstance(required_value, bool) and not isinstance(field_value, bool):
                field_value = self._normalize_bool_value(field_value)

            logger.debug(f"Comparaison pour {self.field_id}: {field_value} == {required_value}")

            # Définir l'état initial
            if field_value != required_value:
                logger.debug(f"Champ {self.field_id} initialement désactivé")
                self.disabled = True
                self.add_class('disabled')
            else:
                logger.debug(f"Champ {self.field_id} initialement activé")
                self.disabled = False
                self.remove_class('disabled')
        else:
            # Par défaut, désactiver si la dépendance n'est pas résolue
            logger.debug(f"Champ dépendant {self.enabled_if['field']} non trouvé pour {self.field_id}, désactivé par défaut")
            self.disabled = True
            self.add_class('disabled')
    
    def _normalize_bool_value(self, value):
        """Normalise une valeur en booléen"""
        if isinstance(value, str):
            return value.lower() in ('true', 't', 'yes', 'y', '1')
        return bool(value)

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