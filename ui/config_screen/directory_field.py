from textual.app import ComposeResult
from textual.widgets import Button, Input
from textual.containers import VerticalGroup, Horizontal
from subprocess import Popen, PIPE
from typing import Any, Optional, Tuple, Dict, List, Union, cast
import os

from .text_field import TextField
from ..utils.logging import get_logger

logger = get_logger('directory_field')

class DirectoryField(TextField):
    """Champ de sélection de répertoire avec un bouton de navigation"""
    
    def __init__(self, source_id: str, field_id: str, field_config: dict, fields_by_id: dict = None, is_global: bool = False):
        """
        Initialisation du champ avec les options spécifiques aux répertoires.
        
        Args:
            source_id: ID de la source (plugin ou config globale)
            field_id: ID du champ
            field_config: Configuration du champ
            fields_by_id: Dictionnaire des champs par ID
            is_global: Indique si c'est un champ global
        """
        # Définir le bouton avant d'appeler super().__init__
        self._browse_button: Optional[Button] = None
        
        # Flag pour suivre les mises à jour
        self._updating_disabled_state = False
        self._pending_disabled_state = None
        self._disabled_initialization_done = False
        
        # Appeler l'initialisation du parent (TextField)
        # Cela initialisera notamment _internal_value et gèrera la validation
        super().__init__(source_id, field_id, field_config, fields_by_id, is_global)
        
        logger.debug(f"Initialisation du champ répertoire {self.field_id}, disabled={getattr(self, 'disabled', False)}")
    
    def compose(self) -> ComposeResult:
        """
        Composition des éléments visuels du champ.
        
        Returns:
            ComposeResult: Résultat de la composition des widgets
        """
        # 1. Récupérer les widgets de base du TextField
        parent_widgets = list(super().compose())
        
        # 2. Rendre les widgets de base
        for widget in parent_widgets:
            yield widget

        # 3. Ajouter le bouton Browse en dehors du conteneur d'input
        self._browse_button = Button(
            "Parcourir...", 
            id=f"browse_{self.field_id}", 
            classes="browse-button"
        )
        
        # Appliquer l'état disabled au bouton si nécessaire
        if hasattr(self, 'disabled') and self.disabled:
            logger.debug(f"Application de l'état disabled au bouton browse lors de la composition pour {self.field_id}")
            self._browse_button.disabled = True
            
        yield self._browse_button
    
    def on_mount(self) -> None:
        """
        Exécuté après création des widgets.
        """
        logger.debug(f"🔴 MONTAGE du champ répertoire {self.field_id}, disabled={getattr(self, 'disabled', False)}")
        
        # Appeler la méthode du parent (TextField) pour la gestion des valeurs en attente
        # et l'application des valeurs stockées dans _internal_value ou _pending_value
        super().on_mount()
        
        # Forcer la mise à jour de l'état disabled pour le bouton de navigation
        if hasattr(self, '_browse_button') and self._browse_button:
            logger.debug(f"Application de l'état disabled={self.disabled} au bouton browse lors du montage pour {self.field_id}")
            self._browse_button.disabled = self.disabled
        
        # Vérifier l'état d'activation selon la dépendance
        self._check_enabled_state()
        
        # Marquer que l'initialisation est terminée
        self._disabled_initialization_done = True
        
        # Si un état est en attente d'application, l'appliquer maintenant
        if self._pending_disabled_state is not None:
            logger.debug(f"Application de l'état en attente disabled={self._pending_disabled_state} pour {self.field_id}")
            self.set_disabled(self._pending_disabled_state)
            self._pending_disabled_state = None
    
    def set_disabled(self, disabled: bool) -> None:
        """
        Désactive ou active à la fois le champ texte et le bouton browse.
        
        Args:
            disabled: True pour désactiver, False pour activer
        """
        # Protection contre les mises à jour récursives
        if self._updating_disabled_state:
            logger.debug(f"🔄 Évitement de récursion dans set_disabled pour {self.field_id}")
            return
            
        # Si l'initialisation n'est pas terminée, stocker l'état pour application ultérieure
        if not hasattr(self, '_disabled_initialization_done') or not self._disabled_initialization_done:
            logger.debug(f"⏳ Initialisation non terminée pour {self.field_id}, état disabled={disabled} mis en attente")
            self._pending_disabled_state = disabled
            return
            
        try:
            self._updating_disabled_state = True
            logger.debug(f"set_disabled appelé pour {self.field_id} avec disabled={disabled}")
            
            # Stocker l'état disabled
            self.disabled = disabled
            
            # Mettre à jour l'état du champ texte
            if hasattr(self, 'input') and self.input:
                logger.debug(f"Mise à jour de l'état du champ texte pour {self.field_id}: disabled={disabled}")
                self.input.disabled = disabled
                if disabled:
                    self.input.add_class('disabled')
                else:
                    self.input.remove_class('disabled')
            
            # Ajouter/supprimer la classe disabled sur le widget lui-même
            if disabled:
                self.add_class('disabled')
            else:
                self.remove_class('disabled')
            
            # Désactiver aussi le bouton browse s'il existe
            if hasattr(self, '_browse_button') and self._browse_button:
                logger.debug(f"Mise à jour de l'état du bouton browse pour {self.field_id}: disabled={disabled}")
                self._browse_button.disabled = disabled
            else:
                logger.debug(f"Bouton browse non encore disponible pour {self.field_id}, l'état disabled={disabled} sera appliqué lors de la composition")
        finally:
            self._updating_disabled_state = False
    
    def _check_enabled_state(self) -> None:
        """
        Vérifie si le champ doit être activé ou désactivé selon ses dépendances.
        Version améliorée avec recherche plus robuste du champ dépendant.
        """
        if not hasattr(self, 'enabled_if') or not self.enabled_if:
            logger.debug(f"Pas de condition enabled_if pour {self.field_id}")
            return
            
        # Récupérer les champs disponibles
        fields_by_id = {}
        if hasattr(self, 'fields_by_id'):
            fields_by_id = self.fields_by_id
            
        dep_field_id = self.enabled_if['field']
        required_value = self.enabled_if.get('value')
        logger.debug(f"🔍 Condition enabled_if pour {self.field_id}: dépend de {dep_field_id} avec valeur requise {required_value} (type: {type(required_value).__name__})")

        # Recherche du champ dépendant avec toutes les méthodes possibles
        dep_field = None
        
        # 1. Recherche directe
        if dep_field_id in fields_by_id:
            dep_field = fields_by_id[dep_field_id]
            logger.debug(f"Champ dépendant trouvé directement: {dep_field_id}")
        
        # 2. Recherche avec le préfixe du source_id (plugin.field_id)
        elif f"{self.source_id}.{dep_field_id}" in fields_by_id:
            dep_field = fields_by_id[f"{self.source_id}.{dep_field_id}"]
            logger.debug(f"Champ dépendant trouvé avec préfixe: {self.source_id}.{dep_field_id}")
            
        # 3. Recherche via un parcours des champs
        else:
            for field_key, field_obj in fields_by_id.items():
                # Vérifier les attributs du champ
                if hasattr(field_obj, 'field_id') and field_obj.field_id == dep_field_id:
                    if hasattr(field_obj, 'source_id') and field_obj.source_id == self.source_id:
                        dep_field = field_obj
                        logger.debug(f"Champ dépendant trouvé par attributs: {field_key}")
                        break

        # Si le champ dépendant n'est pas trouvé
        if not dep_field:
            logger.debug(f"❌ Champ dépendant {dep_field_id} non trouvé pour {self.field_id}")
            return
            
        # Récupérer la valeur du champ dépendant
        if hasattr(dep_field, 'get_value'):
            dep_value = dep_field.get_value()
            logger.debug(f"✅ Valeur récupérée pour {dep_field_id}: {dep_value} (type: {type(dep_value).__name__})")
        elif hasattr(dep_field, 'value'):
            dep_value = dep_field.value
            logger.debug(f"✅ Valeur récupérée via attribut value pour {dep_field_id}: {dep_value}")
        else:
            logger.debug(f"❌ Impossible de récupérer la valeur pour {dep_field_id}")
            return

        # Normaliser les valeurs booléennes pour la comparaison
        normalized_dep_value = self._normalize_bool_value(dep_value)
        normalized_required_value = self._normalize_bool_value(required_value)
        
        logger.debug(f"🔄 Après normalisation: {dep_field_id}={normalized_dep_value} (avant: {dep_value}), requis={normalized_required_value} (avant: {required_value})")
        
        # Déterminer si le champ doit être activé ou désactivé
        should_enable = normalized_dep_value == normalized_required_value
        
        # Mettre à jour l'état disabled si nécessaire
        if self.disabled is not (not should_enable):  # Si l'état actuel ne correspond pas à ce qu'il devrait être
            logger.debug(f"🔄 Mise à jour de l'état disabled pour {self.field_id}: {self.disabled} -> {not should_enable}")
            self.set_disabled(not should_enable)
        else:
            logger.debug(f"✓ L'état disabled pour {self.field_id} est déjà correct: {self.disabled}")

    
    def _normalize_bool_value(self, value: Any) -> Any:
        """
        Normalise une valeur en booléen si possible.
        
        Args:
            value: Valeur à normaliser
            
        Returns:
            Any: Valeur normalisée ou originale si non booléenne
        """
        # Si c'est déjà un booléen, le retourner tel quel
        if isinstance(value, bool):
            return value
            
        # Si c'est une chaîne qui représente un booléen
        if isinstance(value, str):
            if value.lower() in ('true', 't', 'yes', 'y', '1'):
                return True
            elif value.lower() in ('false', 'f', 'no', 'n', '0'):
                return False
                
        # Pour d'autres types, utiliser la conversion standard
        # Mais seulement pour les types compatibles avec les booléens
        if value is not None:
            try:
                return bool(value)
            except:
                pass
                
        # Retourner la valeur originale si non convertible
        return value
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Gestion du clic sur le bouton Browse.
        
        Args:
            event: Événement de bouton pressé
        """
        # Vérifier que c'est bien notre bouton
    
    def validate_input(self, value: str) -> Tuple[bool, str]:
        """
        Validation spécifique pour les chemins de répertoire.
        
        Args:
            value: Valeur à valider
            
        Returns:
            Tuple[bool, str]: (validité, message d'erreur)
        """
        # Si le champ est désactivé, pas de validation nécessaire
        if getattr(self, 'disabled', False):
            return True, ""
        
        # Utiliser d'abord la validation de base (vide, longueur, etc.)
        is_valid, error_msg = super().validate_input(value)
        if not is_valid:
            return is_valid, error_msg
        
        # Validation spécifique aux répertoires
        # Par exemple, vérifier si c'est un chemin existant si 'exists' est spécifié
        if value and self.field_config.get('exists', False):
            import os
            if not os.path.exists(value):
                return False, "Ce répertoire n'existe pas"
            if not os.path.isdir(value):
                return False, "Ce chemin n'est pas un répertoire"
        
        # Si on arrive ici, tout est valide
        return True, ""
    

        if event.button.id != f"browse_{self.field_id}":
            return
            
        logger.debug(f"🔍 Bouton Browse pressé pour {self.field_id}")
        
        # Ne rien faire si le champ est désactivé
        if getattr(self, 'disabled', False):
            logger.debug(f"⚠️ Bouton Browse ignoré car le champ est désactivé")
            return
        
        # Lancer la boîte de dialogue de sélection de répertoire via zenity
        try:
            from subprocess import Popen, PIPE
            import os
            
            # Utiliser le répertoire actuel comme point de départ si déjà défini
            current_dir = self._internal_value if hasattr(self, '_internal_value') and self._internal_value else ""
            
            # Args pour zenity - démarrer dans le répertoire actuel si possible
            zenity_args = ['zenity', '--file-selection', '--directory']
            if current_dir and os.path.isdir(current_dir):
                zenity_args.extend(['--filename', current_dir])
                
            logger.debug(f"Exécution de zenity avec arguments: {zenity_args}")
            process = Popen(zenity_args, stdout=PIPE, stderr=PIPE)
            stdout, stderr = process.communicate()
            
            if stderr:
                logger.debug(f"Zenity stderr: {stderr.decode()}")
                
            # Si réussi, appliquer le répertoire sélectionné
            if process.returncode == 0:
                selected_dir = stdout.decode().strip()
                logger.debug(f"Répertoire sélectionné: '{selected_dir}'")
                
                # Mise à jour de la valeur via notre méthode standard
                if selected_dir and (not hasattr(self, '_internal_value') or selected_dir != self._internal_value):
                    logger.debug(f"Application du répertoire sélectionné pour {self.field_id}")
                    self.set_value(selected_dir)
            else:
                logger.debug(f"Sélection de répertoire annulée ou échouée (code: {process.returncode})")
                    
        except Exception as e:
            logger.error(f"Erreur lors de la sélection du répertoire: {e}")
            import traceback
            logger.error(traceback.format_exc())