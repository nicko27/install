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
        self.field_config = field_config   # Configuration du champ
        self.fields_by_id = fields_by_id or {}  # Champs indexés par ID pour les dépendances
        self.is_global = is_global         # Indique si c'est un champ global ou plugin

        # Attributs pour la gestion des dépendances
        if 'enabled_if' in field_config:
            self.enabled_if = field_config['enabled_if']
            self._original_default = field_config.get('default')
        else:
            self.enabled_if = None
            self._original_default = None
            
        # Nom de la variable pour l'export (peut être différent de l'ID)
        self.variable_name = field_config.get('variable', field_id)
        
        # Gestion des dépendances pour les valeurs dynamiques
        if 'depends_on' in field_config:
            self.depends_on = field_config['depends_on']
            logger.debug(f"Champ {self.field_id} dépend de {self.depends_on}")
        else:
            self.depends_on = None

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
            sys.path.append(os.path.dirname(script_path))
            
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
                
            # Traiter la valeur selon son type
            if isinstance(value, dict):
                # Extraire une clé spécifique si définie
                value_key = dynamic_config.get('value')
                if value_key and value_key in value:
                    return value[value_key]
                    
                # Sinon prendre la première valeur
                if value:
                    return next(iter(value.values()))
                    
            # Valeur non-dictionnaire
            return value
            
        # Cas 2: Résultat est un dictionnaire
        elif isinstance(result, dict):
            value_key = dynamic_config.get('value')
            if value_key and value_key in result:
                return result[value_key]
                
            # Sinon prendre la première valeur
            if result:
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
                yield Label(f"{label} *", classes="field-label required-field")
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
            
        dep_field = self.fields_by_id.get(self.enabled_if['field'])
        logger.debug(f"Vérification état initial pour {self.field_id}: enabled_if={self.enabled_if}, "
                    f"champ dépendant={dep_field and dep_field.field_id}")

        # Vérifier si le champ dépendant existe
        if dep_field:
            # Récupérer les valeurs pour la comparaison
            field_value = dep_field.value
            required_value = self.enabled_if.get('value')

            # Convertir en booléens si nécessaire pour la comparaison
            if isinstance(required_value, bool) and not isinstance(field_value, bool):
                if isinstance(field_value, str):
                    field_value = field_value.lower() in ('true', 't', 'yes', 'y', '1')
                else:
                    field_value = bool(field_value)

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