from textual.app import ComposeResult
from textual.widgets import Input
from textual.containers import VerticalGroup
from typing import Optional, Tuple, Any, cast
from .config_field import ConfigField
from ..utils.logging import get_logger

logger = get_logger('text_field')

class TextField(ConfigField):
    """Champ texte avec mécanisme de mise à jour contrôlé"""
    
    def __init__(self, source_id: str, field_id: str, field_config: dict, fields_by_id: dict = None, is_global: bool = False):
        """Initialisation du champ texte"""
        # Initialiser les propriétés pour le contrôle des mises à jour AVANT d'appeler super().__init__
        # car ConfigField va accéder à self.value qui dépend de ces propriétés
        self._internal_value: str = ""            # Valeur interne, toujours disponible
        self._updating_internally: bool = False   # Flag pour bloquer les mises à jour cycliques
        self._pending_value: Optional[str] = None # Valeur en attente (widget pas encore monté)
        self._update_counter: int = 0            # Compteur pour détecter les cascades
        
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
        """Création des éléments visuels du champ"""
        # Composer les éléments de base (label, etc.)
        yield from super().compose()
        
        # Essayer de récupérer la valeur de la séquence avant de créer le widget
        self._try_load_sequence_value()
        
        # Conteneur pour l'input
        with VerticalGroup(classes="input-container", id=f"container_{self.field_id}"):
            # Créer le widget Input avec la valeur interne actuelle
            input_value = self._internal_value
            logger.debug(f"💻 Création du widget input pour {self.field_id} avec valeur: '{input_value}'")
            
            self.input = Input(
                placeholder=self.field_config.get('placeholder', ''),
                value=input_value,
                id=f"input_{self.field_id}"
            )
            # État initial: activé
            self.input.disabled = False
            self.input.remove_class('disabled')

            # Si le champ est désactivé via enabled_if
            if self.disabled:
                logger.debug(f"Champ {self.field_id} désactivé initialement")
                self.input.disabled = True
                self.input.add_class('disabled')
            yield self.input
            
    def _try_load_sequence_value(self):
        """Essaie de charger la valeur depuis la configuration prédéfinie (séquence)"""
        try:
            # Trouver l'écran de configuration
            from .config_screen import PluginConfig
            config_screen = None
            
            # Rechercher l'écran de configuration dans la hiérarchie des ancêtres
            app = self.app if hasattr(self, 'app') and self.app else None
            if app and hasattr(app, 'screen') and isinstance(app.screen, PluginConfig):
                config_screen = app.screen
            
            if not config_screen or not hasattr(config_screen, 'current_config'):
                return
            
            # Récupérer le conteneur parent
            from .plugin_config_container import PluginConfigContainer
            parent = next((a for a in self.ancestors_with_self if isinstance(a, PluginConfigContainer)), None)
            if not parent or not hasattr(parent, 'id'):
                return
            
            # Récupérer l'ID de l'instance du plugin
            plugin_instance_id = parent.id.replace('plugin_', '')
            if plugin_instance_id not in config_screen.current_config:
                return
                
            # Récupérer la configuration prédéfinie
            predefined_config = config_screen.current_config[plugin_instance_id]
            
            # Obtenir la variable ou config, selon le format
            variable_name = self.field_config.get('variable', self.field_id)
            
            # Chercher dans 'config' (nouveau format)
            if 'config' in predefined_config and variable_name in predefined_config['config']:
                value = predefined_config['config'][variable_name]
                if value is not None:
                    logger.debug(f"💾 Valeur trouvée dans séquence pour {self.field_id}: '{value}'")
                    self._internal_value = str(value) if value is not None else ""
                    return
                    
            # Format 2: Chercher directement (ancien format)
            elif variable_name in predefined_config:
                value = predefined_config[variable_name]
                if value is not None:
                    logger.debug(f"💾 Valeur trouvée dans séquence (ancien format) pour {self.field_id}: '{value}'")
                    self._internal_value = str(value) if value is not None else ""
                    return
                    
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la valeur de séquence pour {self.field_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def on_mount(self) -> None:
        """Exécuté après création des widgets"""
        logger.debug(f"🚨 MONTAGE du champ {self.field_id}")
        
        # Appliquer une valeur en attente si elle existe
        if self._pending_value is not None:
            logger.debug(f"Application de la valeur en attente '{self._pending_value}' pour {self.field_id}")
            self._set_widget_value(self._pending_value)
            self._pending_value = None  # Réinitialiser après usage
        else:
            logger.debug(f"Pas de valeur en attente pour {self.field_id}, valeur actuelle: '{self._internal_value}'")
        
        # Vérifier la validation au montage
        self._validate_and_update_ui(self._internal_value)
    
    def validate_input(self, value: str) -> Tuple[bool, str]:
        """Validation selon les règles configurées"""
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
    
    def _validate_and_update_ui(self, value: str) -> bool:
        """Valide la valeur et met à jour l'interface utilisateur en conséquence"""
        # Seulement si le widget existe
        if not hasattr(self, 'input'):
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
    
    def _set_widget_value(self, value: str) -> None:
        """Met à jour le widget avec la valeur donnée, sans déclencher d'événements"""
        if not hasattr(self, 'input'):
            logger.debug(f"Widget input non créé pour {self.field_id}, stockage de '{value}' en attente")
            self._pending_value = value
            return
            
        # Vérifier si la valeur actuelle est différente
        current_widget_value = self.input.value
        if current_widget_value == value:
            logger.debug(f"Widget déjà à la valeur '{value}' pour {self.field_id}, rien à faire")
            return
            
        logger.debug(f"Mise à jour du widget pour {self.field_id}: '{current_widget_value}' → '{value}'")
        self.input.value = value
        
        # Valider et mettre à jour l'UI
        self._validate_and_update_ui(value)
    
    def set_value(self, value: str, update_input: bool = True, update_dependencies: bool = True) -> bool:
        """Définit la valeur du champ avec mécanisme anti-cycles complet"""
        # Conversion à la chaîne pour uniformité
        value_str = str(value) if value is not None else ""
        
        # ===== PHASE 1: Vérifications préliminaires =====
        self._update_counter += 1
        logger.debug(f"🔔 [{self._update_counter}] set_value({value_str}) pour {self.field_id}, update_input={update_input}")
        
        # Vérification 1: Prévenir les mises à jour récursives
        if self._updating_internally:
            logger.debug(f"⚠️ Déjà en cours de mise à jour pour {self.field_id}, évitement cycle")
            return True
            
        # Vérification 2: Valeur identique à la valeur interne actuelle
        if self._internal_value == value_str:
            logger.debug(f"✓ Valeur interne déjà à '{value_str}' pour {self.field_id}")
            return True
        
        # Marquer le début de la mise à jour
        self._updating_internally = True
        
        try:
            # ===== PHASE 2: Mise à jour de la valeur interne =====
            old_value = self._internal_value
            self._internal_value = value_str
            logger.debug(f"💾 Valeur interne mise à jour pour {self.field_id}: '{old_value}' → '{value_str}'")
            
            # ===== PHASE 3: Mise à jour du widget si demandé =====
            if update_input:
                self._set_widget_value(value_str)
                
            # ===== PHASE 4: Mise à jour des dépendances si demandé =====
            if update_dependencies:
                from .config_container import ConfigContainer
                parent = next((a for a in self.ancestors_with_self if isinstance(a, ConfigContainer)), None)
                if parent:
                    logger.debug(f"🔗 Notification des dépendances pour {self.field_id}")
                    parent.update_dependent_fields(self)
                       
            logger.debug(f"✅ set_value réussi pour {self.field_id}")
            return True
            
        except Exception as e:
            # Capturer les exceptions pour éviter de bloquer l'interface
            logger.error(f"❌ Erreur dans set_value pour {self.field_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
            
        finally:
            # CRUCIAL: Toujours réinitialiser le flag pour permettre des mises à jour futures
            self._updating_internally = False
    
    def on_input_changed(self, event: Input.Changed) -> None:
        """Gestionnaire d'événement quand l'utilisateur modifie l'input"""
        # Vérifier que c'est bien notre input qui a changé
        if event.input.id != f"input_{self.field_id}":
            return
            
        # Si nous sommes en train de mettre à jour l'input programmatiquement, ignorer
        if self._updating_internally:
            logger.debug(f"⚠️ Ignorer on_input_changed pendant mise à jour pour {self.field_id}")
            return
            
        # Valeur différente de la valeur interne?
        value = str(event.value) if event.value is not None else ""
        if self._internal_value == value:
            logger.debug(f"✓ on_input_changed: valeur déjà à jour pour {self.field_id}: '{value}'")
            return
            
        logger.debug(f"👁️ on_input_changed pour {self.field_id}: '{self._internal_value}' → '{value}'")
        # Appeler set_value sans mettre à jour l'input (déjà fait par l'utilisateur)
        self.set_value(value, update_input=False)
    
    # Interface de propriété pour accès simplifié
    @property
    def value(self) -> str:
        """Accès à la valeur interne"""
        return self._internal_value
        
    @value.setter
    def value(self, new_value: Any) -> None:
        """Modification de la valeur via l'accesseur"""
        # Déléguer à set_value, sans notification pour éviter les cycles
        if self._updating_internally:
            self._internal_value = str(new_value) if new_value is not None else ""
        else:
            self.set_value(new_value, update_dependencies=False)
    
    def get_value(self) -> str:
        """Récupération de la valeur pour l'export"""
        return self._internal_value