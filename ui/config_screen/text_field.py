from textual.app import ComposeResult
from textual.widgets import Input
from textual.containers import VerticalGroup
from typing import Optional, Tuple, Any, Dict, List, Union, cast
import traceback

from .config_field import ConfigField
from ..utils.logging import get_logger

logger = get_logger('text_field')

class TextField(ConfigField):
    """
    Champ de configuration pour saisir du texte.
    
    Cette classe permet de créer un widget d'entrée texte dans l'interface
    de configuration. Elle gère la validation, les dépendances, et 
    les mécanismes anti-cycles pour les mises à jour.
    """
    
    def __init__(self, source_id: str, field_id: str, field_config: Dict[str, Any], 
                 fields_by_id: Optional[Dict[str, Any]] = None, is_global: bool = False,
                 instance_id: Optional[int] = None):
        """
        Initialise un champ de texte.
        
        Args:
            source_id: ID du plugin ou de la source
            field_id: ID unique du champ
            field_config: Configuration du champ
            fields_by_id: Dictionnaire des champs par ID (pour les dépendances)
            is_global: Indique si le champ est global
            instance_id: ID d'instance (optionnel)
        """
        # Initialiser les propriétés pour le contrôle des mises à jour AVANT d'appeler super().__init__
        # car ConfigField va accéder à self.value qui dépend de ces propriétés
        self._internal_value: str = ""            # Valeur interne, toujours disponible
        self._updating_internally: bool = False   # Flag pour bloquer les mises à jour cycliques
        self._pending_value: Optional[str] = None # Valeur en attente (widget pas encore monté)
        self._update_counter: int = 0             # Compteur pour détecter les cascades
        
        # Maintenant appeler l'initialisation du parent
        super().__init__(source_id, field_id, field_config, fields_by_id, is_global)
        
        # Si la valeur a été modifiée par ConfigField via self.value, elle sera déjà dans self._internal_value
        # Sinon, initialiser avec la valeur par défaut
        if not self._internal_value and 'default' in self.field_config:
            initial_value = self.field_config.get('default', '')
            if initial_value is not None:
                self._internal_value = str(initial_value)
                logger.debug(f"Valeur initiale pour {self.field_id}: '{self._internal_value}'")
    
    def compose(self) -> ComposeResult:
        """
        Compose l'interface du champ de texte.
        
        Returns:
            ComposeResult: Résultat de la composition
        """
        try:
            # Composer les éléments communs depuis la classe parente
            yield from super().compose()
            
            # Essayer de charger la valeur depuis une séquence si disponible
            self._try_load_sequence_value()
            
            # Conteneur pour l'input
            with VerticalGroup(classes="input-container", id=f"container_{self.field_id}"):
                # Créer le widget Input avec la valeur interne actuelle
                input_value = self._internal_value
                logger.debug(f"Création du widget input pour {self.field_id} avec valeur: '{input_value}'")
                
                self.input = Input(
                    placeholder=self.field_config.get('placeholder', ''),
                    value=input_value,
                    id=f"input_{self.source_id}_{self.field_id}"
                )
                
                # État initial: activé sauf si disabled est défini
                self.input.disabled = self.disabled
                if self.disabled:
                    self.input.add_class('disabled')
                    logger.debug(f"Champ {self.field_id} désactivé initialement")
                
                yield self.input
                
        except Exception as e:
            logger.error(f"Erreur lors de la composition du champ texte {self.field_id}: {e}")
            logger.error(traceback.format_exc())
            
            # En cas d'erreur, créer un widget minimal
            with VerticalGroup(classes="input-container error"):
                yield Input(
                    id=f"input_{self.source_id}_{self.field_id}_error",
                    value="",
                    disabled=True,
                    classes="error"
                )
            
    def _try_load_sequence_value(self) -> None:
        """
        Essaie de charger la valeur depuis une configuration de séquence.
        """
        try:
            # Trouver l'écran de configuration
            from .config_screen import PluginConfig
            config_screen = None
            
            # Rechercher l'écran de configuration dans la hiérarchie
            app = self.app if hasattr(self, 'app') and self.app else None
            if app and hasattr(app, 'screen') and isinstance(app.screen, PluginConfig):
                config_screen = app.screen
            
            if not config_screen or not hasattr(config_screen, 'current_config'):
                logger.debug(f"Pas d'écran de configuration trouvé pour {self.field_id}")
                return
            
            # Récupérer le conteneur parent
            from .plugin_config_container import PluginConfigContainer
            parent = self._get_parent_container()
            if not parent or not hasattr(parent, 'id'):
                logger.debug(f"Pas de conteneur parent trouvé pour {self.field_id}")
                return
            
            # Récupérer l'ID de l'instance du plugin
            plugin_instance_id = parent.id.replace('plugin_', '')
            if plugin_instance_id not in config_screen.current_config:
                logger.debug(f"Pas de configuration pour l'instance {plugin_instance_id}")
                return
                
            # Récupérer la configuration de la séquence
            sequence_config = config_screen.current_config[plugin_instance_id]
            
            # Déterminer le nom de la variable (utiliser variable_name si défini, sinon field_id)
            variable_name = getattr(self, 'variable_name', 
                                   self.field_config.get('variable', self.field_id))
            
            # Chercher la valeur dans la configuration
            value = None
            
            # Format 1: Chercher dans 'config' (nouveau format)
            if 'config' in sequence_config and variable_name in sequence_config['config']:
                value = sequence_config['config'][variable_name]
                logger.debug(f"Valeur trouvée dans séquence pour {variable_name}: '{value}'")
                    
            # Format 2: Chercher directement (ancien format)
            elif variable_name in sequence_config:
                value = sequence_config[variable_name]
                logger.debug(f"Valeur trouvée dans séquence (ancien format) pour {variable_name}: '{value}'")
            
            # Mettre à jour la valeur si trouvée
            if value is not None:
                self._internal_value = str(value)
                logger.debug(f"Valeur pour {self.field_id} définie à: '{self._internal_value}'")
                    
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la valeur de séquence pour {self.field_id}: {e}")
            logger.error(traceback.format_exc())
    
    def on_mount(self) -> None:
        """
        Exécuté après création des widgets.
        """
        try:
            logger.debug(f"Montage du champ {self.field_id}")
            
            # Appliquer une valeur en attente si elle existe
            if self._pending_value is not None:
                logger.debug(f"Application de la valeur en attente '{self._pending_value}' pour {self.field_id}")
                self._set_widget_value(self._pending_value)
                self._pending_value = None  # Réinitialiser après usage
            else:
                logger.debug(f"Pas de valeur en attente pour {self.field_id}, valeur actuelle: '{self._internal_value}'")
            
            # Vérifier la validation au montage
            self._validate_and_update_ui(self._internal_value)
            
        except Exception as e:
            logger.error(f"Erreur lors du montage du champ {self.field_id}: {e}")
            logger.error(traceback.format_exc())
    
    def validate_input(self, value: str) -> Tuple[bool, str]:
        """
        Valide une valeur selon les règles configurées.
        
        Args:
            value: Valeur à valider
            
        Returns:
            Tuple[bool, str]: (est_valide, message_erreur)
        """
        try:
            # Si le champ est désactivé, pas de validation nécessaire
            if self.disabled:
                return True, ""
    
            # Champ obligatoire
            if self.field_config.get('not_empty', False) and not value:
                return False, "Ce champ ne peut pas être vide"
    
            # Longueur minimale
            min_length = self.field_config.get('min_length')
            if min_length and len(value) < min_length:
                return False, f"La longueur minimale est de {min_length} caractères"
    
            # Longueur maximale
            max_length = self.field_config.get('max_length')
            if max_length and len(value) > max_length:
                return False, f"La longueur maximale est de {max_length} caractères"
    
            # Espaces interdits
            if self.field_config.get('validate') == 'no_spaces' and ' ' in value:
                return False, "Les espaces ne sont pas autorisés"
    
            # Valide par défaut
            return True, ""
            
        except Exception as e:
            logger.error(f"Erreur lors de la validation pour {self.field_id}: {e}")
            logger.error(traceback.format_exc())
            return False, f"Erreur lors de la validation: {str(e)}"
    
    def _validate_and_update_ui(self, value: str) -> bool:
        """
        Valide la valeur et met à jour l'interface utilisateur en conséquence.
        
        Args:
            value: Valeur à valider
            
        Returns:
            bool: True si la valeur est valide
        """
        try:
            # Seulement si le widget existe
            if not hasattr(self, 'input') or not self.input:
                return True
                
            # Valider
            is_valid, error_msg = self.validate_input(value)
            
            # Mettre à jour l'interface selon la validation
            if is_valid:
                self.input.remove_class('error')
                self.input.tooltip = None
            else:
                self.input.add_class('error')
                self.input.tooltip = error_msg
                logger.debug(f"Validation échouée pour {self.field_id}: {error_msg}")
                
            return is_valid
            
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'UI pour {self.field_id}: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def _set_widget_value(self, value: str) -> None:
        """
        Met à jour le widget avec la valeur donnée, sans déclencher d'événements.
        
        Args:
            value: Nouvelle valeur à appliquer
        """
        try:
            # Gérer le cas où le widget n'existe pas encore
            if not hasattr(self, 'input') or not self.input:
                logger.debug(f"Widget input non créé pour {self.field_id}, stockage de '{value}' en attente")
                self._pending_value = value
                return
                
            # Vérifier si la valeur actuelle est différente
            current_widget_value = self.input.value
            if current_widget_value == value:
                logger.debug(f"Widget déjà à la valeur '{value}' pour {self.field_id}")
                return
                
            logger.debug(f"Mise à jour du widget pour {self.field_id}: '{current_widget_value}' → '{value}'")
            self.input.value = value
            
            # Valider et mettre à jour l'UI
            self._validate_and_update_ui(value)
            
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du widget pour {self.field_id}: {e}")
            logger.error(traceback.format_exc())
    
    def set_value(self, value: str, update_input: bool = True, update_dependencies: bool = True) -> bool:
        """
        Définit la valeur du champ avec mécanisme anti-cycles complet.
        
        Args:
            value: Nouvelle valeur (sera convertie en chaîne)
            update_input: Si True, met à jour le widget
            update_dependencies: Si True, notifie les dépendances
            
        Returns:
            bool: True si la valeur a été mise à jour avec succès
        """
        try:
            # Conversion à la chaîne pour uniformité
            value_str = str(value) if value is not None else ""
            
            # ===== PHASE 1: Vérifications préliminaires =====
            self._update_counter += 1
            logger.debug(f"[{self._update_counter}] set_value({value_str}) pour {self.field_id}, update_input={update_input}")
            
            # Vérification 1: Prévenir les mises à jour récursives
            if self._updating_internally:
                logger.debug(f"Déjà en cours de mise à jour pour {self.field_id}, évitement cycle")
                return True
                
            # Vérification 2: Valeur identique à la valeur interne actuelle
            if self._internal_value == value_str:
                logger.debug(f"Valeur interne déjà à '{value_str}' pour {self.field_id}")
                return True
            
            # Marquer le début de la mise à jour
            self._updating_internally = True
            
            try:
                # ===== PHASE 2: Mise à jour de la valeur interne =====
                old_value = self._internal_value
                self._internal_value = value_str
                logger.debug(f"Valeur interne mise à jour pour {self.field_id}: '{old_value}' → '{value_str}'")
                
                # ===== PHASE 3: Mise à jour du widget si demandé =====
                if update_input:
                    self._set_widget_value(value_str)
                    
                # ===== PHASE 4: Mise à jour des dépendances si demandé =====
                if update_dependencies:
                    self._notify_dependencies()
                       
                logger.debug(f"set_value réussi pour {self.field_id}")
                return True
                
            finally:
                # CRUCIAL: Toujours réinitialiser le flag pour permettre des mises à jour futures
                self._updating_internally = False
                
        except Exception as e:
            # Capturer les exceptions pour éviter de bloquer l'interface
            logger.error(f"Erreur dans set_value pour {self.field_id}: {e}")
            logger.error(traceback.format_exc())
            return False

    def on_input_changed(self, event: Input.Changed) -> None:
        """
        Gère les changements d'entrée utilisateur.
        
        Args:
            event: Événement de changement d'entrée
        """
        try:
            # Vérifier que c'est bien notre input qui a changé
            expected_id = f"input_{self.source_id}_{self.field_id}"
            if event.input.id != expected_id:
                return
                
            # Si nous sommes déjà en train de mettre à jour l'input, ignorer
            if self._updating_internally:
                logger.debug(f"Ignorer on_input_changed pendant mise à jour pour {self.field_id}")
                return
                
            # Récupérer la nouvelle valeur
            new_value = str(event.value) if event.value is not None else ""
            
            # Si la valeur n'a pas changé par rapport à notre valeur interne, ne rien faire
            if self._internal_value == new_value:
                logger.debug(f"Valeur déjà à '{new_value}' pour {self.field_id}")
                return
                
            logger.debug(f"Changement d'entrée pour {self.field_id}: '{self._internal_value}' → '{new_value}'")
            
            # Mise à jour de la valeur sans mettre à jour l'input (l'utilisateur l'a déjà modifié)
            self.set_value(new_value, update_input=False)
            
        except Exception as e:
            logger.error(f"Erreur lors du traitement du changement d'entrée pour {self.field_id}: {e}")
            logger.error(traceback.format_exc())
    
    @property
    def value(self) -> str:
        """
        Récupère la valeur actuelle du champ.
        
        Returns:
            str: Valeur actuelle
        """
        return self._internal_value
    
    @value.setter
    def value(self, new_value: Any) -> None:
        """
        Définit la valeur du champ via la propriété value.
        
        Args:
            new_value: Nouvelle valeur à définir
        """
        self.set_value(new_value)
    
    def get_value(self) -> str:
        """
        Récupère la valeur actuelle du champ pour l'API externe.
        
        Returns:
            str: Valeur actuelle
        """
        return self._internal_value
        
    def _toggle_field_state(self, is_enabled: bool) -> None:
        """
        Active ou désactive le champ.
        
        Args:
            is_enabled: True pour activer, False pour désactiver
        """
        try:
            self.disabled = not is_enabled
            
            # Mettre à jour le widget
            if hasattr(self, 'input') and self.input:
                self.input.disabled = not is_enabled
                
                if is_enabled:
                    self.input.remove_class('disabled')
                else:
                    self.input.add_class('disabled')
                
            logger.debug(f"État du champ {self.field_id} défini à: {'activé' if is_enabled else 'désactivé'}")
            
        except Exception as e:
            logger.error(f"Erreur lors du changement d'état du champ {self.field_id}: {e}")
            logger.error(traceback.format_exc())
    
    def _toggle_internal_widgets(self, is_enabled: bool) -> None:
        """
        Active ou désactive les widgets internes du champ.
        
        Args:
            is_enabled: True pour activer, False pour désactiver
        """
        try:
            if hasattr(self, 'input') and self.input:
                self.input.disabled = not is_enabled
                
                if is_enabled:
                    self.input.remove_class('disabled')
                else:
                    self.input.add_class('disabled')
                    
        except Exception as e:
            logger.error(f"Erreur lors du toggle des widgets internes de {self.field_id}: {e}")
            logger.error(traceback.format_exc())
    
    def _notify_dependencies(self) -> None:
        """
        Notifie les dépendances du changement de valeur.
        Utilise la méthode améliorée qui recherche le conteneur parent.
        """
        try:
            # Utiliser la méthode améliorée de récupération du conteneur parent
            parent = self._get_parent_container()
            
            if parent and hasattr(parent, 'update_dependent_fields'):
                logger.debug(f"Notification des dépendances depuis {self.unique_id}")
                parent.update_dependent_fields(self)
            else:
                logger.warning(f"Pas de conteneur parent avec update_dependent_fields trouvé pour {self.field_id}")
                
        except Exception as e:
            logger.error(f"Erreur lors de la notification des dépendances pour {self.field_id}: {e}")
            logger.error(traceback.format_exc())