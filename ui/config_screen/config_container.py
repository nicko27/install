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
        self.fields_by_id = fields_by_id            # Tous les champs référencés par ID
        self.config_fields = config_fields          # Configurations des champs

        # Structures de dépendances (mappings directs)
        self.enabled_if_map = {}     # {field_id: {dep_field_id: required_value}}
        self.value_deps_map = {}     # {field_id: dep_field_id}
        self.dynamic_options_map = {}  # {field_id: {dep_fields: [field_ids], args: [arg_configs]}}

        # Structures miroirs (mappings inversés)
        self.mirror_enabled_if = {}    # {field_id: [fields qui dépendent de field_id pour enabled_if]}
        self.mirror_value_deps = {}    # {field_id: [fields qui dépendent de field_id pour leur valeur]}
        self.mirror_dynamic_options = {} # {field_id: [fields qui dépendent de field_id pour leurs options]}

        # État interne
        self._updating_dependencies = False  # Flag pour éviter les cycles
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
            # Création des champs
            for field_config in self.config_fields:
                field = self._create_field(field_config)
                if field:
                    yield field

        # Après la création de tous les champs, analyser leurs dépendances
        # L'analyse est déplacée après la création pour avoir tous les champs disponibles
        self._analyze_field_dependencies()

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

        # Utiliser l'ID unique s'il est disponible pour éviter les conflits entre instances
        unique_id = field_config.get('unique_id', field_id)

        field_type = field_config.get('type', 'text')
        logger.debug(f"Création du champ {field_id} (unique_id: {unique_id}) de type {field_type}")

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

            # Enregistrer le champ dans le dictionnaire global
            self.fields_by_id[unique_id] = field

            return field

        except Exception as e:
            logger.error(f"Erreur lors de la création du champ {field_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _analyze_field_dependencies(self) -> None:
        """
        Analyse les dépendances entre tous les champs du conteneur.
        Cette méthode construit les dictionnaires de dépendances directes et inversées.
        """
        logger.debug(f"Analyse des dépendances pour {self.source_id}")

        # Réinitialiser les dictionnaires de dépendances
        self.enabled_if_map = {}
        self.value_deps_map = {}
        self.dynamic_options_map = {}
        self.mirror_enabled_if = {}
        self.mirror_value_deps = {}
        self.mirror_dynamic_options = {}

        # Parcourir tous les champs pour collecter les dépendances
        for field_id, field in self.fields_by_id.items():
            # Ignorer les champs qui n'appartiennent pas à ce conteneur
            if not hasattr(field, 'source_id') or field.source_id != self.source_id:
                continue

            # Vérifier les dépendances de type 'enabled_if'
            if hasattr(field, 'dependencies') and field.dependencies['enabled_if']:
                enabled_if = field.dependencies['enabled_if']
                dep_field_id = enabled_if['field_id']
                required_value = enabled_if['required_value']

                # Enregistrer la dépendance directe
                if field_id not in self.enabled_if_map:
                    self.enabled_if_map[field_id] = {}
                self.enabled_if_map[field_id][dep_field_id] = required_value

                # Enregistrer la dépendance inverse (miroir)
                if dep_field_id not in self.mirror_enabled_if:
                    self.mirror_enabled_if[dep_field_id] = []
                self.mirror_enabled_if[dep_field_id].append(field_id)

                logger.debug(f"Dépendance enabled_if: {field_id} dépend de {dep_field_id}={required_value}")

            # Vérifier les dépendances de type 'depends_on' (valeur)
            if hasattr(field, 'dependencies') and field.dependencies['depends_on']:
                dep_field_id = field.dependencies['depends_on']

                # Enregistrer la dépendance directe
                self.value_deps_map[field_id] = dep_field_id

                # Enregistrer la dépendance inverse (miroir)
                if dep_field_id not in self.mirror_value_deps:
                    self.mirror_value_deps[dep_field_id] = []
                self.mirror_value_deps[dep_field_id].append(field_id)

                logger.debug(f"Dépendance de valeur: {field_id} dépend de {dep_field_id}")

            # Vérifier les dépendances de type 'dynamic_options'
            if hasattr(field, 'dependencies') and field.dependencies['dynamic_options']:
                dynamic_options = field.dependencies['dynamic_options']

                # Initialiser la structure pour ce champ
                self.dynamic_options_map[field_id] = {
                    'dep_fields': [],
                    'args': dynamic_options.get('args', [])
                }

                # Collecter tous les champs dont dépendent les options
                for arg in dynamic_options.get('args', []):
                    if 'field_id' in arg:
                        dep_field_id = arg['field_id']

                        # Ajouter à la liste des dépendances
                        if dep_field_id not in self.dynamic_options_map[field_id]['dep_fields']:
                            self.dynamic_options_map[field_id]['dep_fields'].append(dep_field_id)

                        # Enregistrer la dépendance inverse (miroir)
                        if dep_field_id not in self.mirror_dynamic_options:
                            self.mirror_dynamic_options[dep_field_id] = []
                        if field_id not in self.mirror_dynamic_options[dep_field_id]:
                            self.mirror_dynamic_options[dep_field_id].append(field_id)

                        logger.debug(f"Dépendance dynamic_options: {field_id} dépend de {dep_field_id}")

        logger.debug(f"Analyse des dépendances terminée: {len(self.enabled_if_map)} enabled_if, " +
                   f"{len(self.value_deps_map)} value_deps, {len(self.dynamic_options_map)} dynamic_options")

    def update_dependent_fields(self, source_field: Widget) -> None:
        """
        Met à jour tous les champs qui dépendent d'un champ spécifique.
        Cette méthode est appelée quand un champ change de valeur.

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

            # Récupérer les identifiants du champ source
            source_field_id = getattr(source_field, 'field_id', None)
            source_unique_id = getattr(source_field, 'unique_id', source_field_id)

            if not source_field_id:
                logger.warning("Impossible de mettre à jour les dépendances: champ source sans field_id")
                return

            logger.debug(f"Mise à jour des champs dépendant de {source_field_id} (unique_id: {source_unique_id})")

            # 1. METTRE À JOUR LES ÉTATS ENABLED/DISABLED
            self._update_enabled_if_dependencies(source_field_id, source_unique_id, source_field)

            # 2. METTRE À JOUR LES OPTIONS DYNAMIQUES
            self._update_dynamic_options_dependencies(source_field_id, source_unique_id, source_field)

            # 3. METTRE À JOUR LES VALEURS DÉPENDANTES
            self._update_value_dependencies(source_field_id, source_unique_id, source_field)

            # 4. TRAITER LES SUPPRESSIONS DE CHAMPS SI NÉCESSAIRE
            self.process_fields_to_remove()

            logger.debug(f"Mise à jour des dépendances terminée pour {source_field_id}")

        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour des dépendances: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            # CRUCIAL: Toujours réinitialiser le flag pour permettre des mises à jour futures
            self._updating_dependencies = False

    def process_fields_to_remove(self) -> None:
        """
        Traite les champs à supprimer suite aux mises à jour de dépendances.
        """
        if not hasattr(self, '_fields_to_remove') or not self._fields_to_remove:
            return

        logger.debug(f"Traitement de {len(self._fields_to_remove)} champs à supprimer")

        # Copier la liste pour éviter les problèmes de modification pendant l'itération
        fields_to_remove = set(self._fields_to_remove)

        # Parcourir les champs à supprimer
        for field_id in fields_to_remove:
            # Vérifier si le champ existe encore
            if field_id in self.fields_by_id:
                field = self.fields_by_id[field_id]

                # Supprimer des structures de dépendances
                if field_id in self.enabled_if_map:
                    del self.enabled_if_map[field_id]
                if field_id in self.value_deps_map:
                    del self.value_deps_map[field_id]
                if field_id in self.dynamic_options_map:
                    del self.dynamic_options_map[field_id]

                # Supprimer des structures miroirs
                for mirror_dict in [self.mirror_enabled_if, self.mirror_value_deps, self.mirror_dynamic_options]:
                    for dep_id, deps in list(mirror_dict.items()):
                        if field_id in deps:
                            deps.remove(field_id)

                # Supprimer du dictionnaire des champs
                del self.fields_by_id[field_id]

                # Supprimer de l'interface si le champ est un enfant direct
                if field in self.children:
                    field.remove()

                logger.debug(f"Champ {field_id} supprimé")

        # Réinitialiser la liste des champs à supprimer
        self._fields_to_remove.clear()

    def _update_enabled_if_dependencies(self, source_field_id: str, source_unique_id: str, source_field: Widget) -> None:
        """
        Met à jour l'état enabled/disabled des champs dont l'activation dépend du champ source.

        Args:
            source_field_id: Identifiant du champ source
            source_unique_id: Identifiant unique du champ source
            source_field: Widget du champ source
        """
        # Utiliser les dictionnaires miroirs pour une recherche directe
        dependent_fields = []

        # Chercher dans le dictionnaire miroir avec l'ID du champ
        if source_field_id in self.mirror_enabled_if:
            dependent_fields.extend(self.mirror_enabled_if[source_field_id])

        # Chercher aussi avec l'ID unique si différent
        if source_unique_id != source_field_id and source_unique_id in self.mirror_enabled_if:
            dependent_fields.extend(self.mirror_enabled_if[source_unique_id])

        # Si aucun champ dépendant trouvé, sortir rapidement
        if not dependent_fields:
            return

        # Récupérer la valeur actuelle du champ source
        source_value = self._get_field_value(source_field)
        logger.debug(f"Mise à jour de {len(dependent_fields)} champs enabled_if dépendant de {source_field_id}={source_value}")

        # Mettre à jour chaque champ dépendant
        for dep_field_id in dependent_fields:
            # Récupérer le champ dépendant
            dependent_field = self.fields_by_id.get(dep_field_id)
            if not dependent_field:
                continue

            # Récupérer la valeur requise pour l'activation
            required_value = None
            if dep_field_id in self.enabled_if_map and source_field_id in self.enabled_if_map[dep_field_id]:
                required_value = self.enabled_if_map[dep_field_id][source_field_id]
            elif dep_field_id in self.enabled_if_map and source_unique_id in self.enabled_if_map[dep_field_id]:
                required_value = self.enabled_if_map[dep_field_id][source_unique_id]

            if required_value is None:
                continue

            # Normaliser les valeurs pour la comparaison
            normalized_source_value = self._normalize_value_for_comparison(source_value)
            normalized_required_value = self._normalize_value_for_comparison(required_value)

            # Déterminer si le champ doit être activé
            should_enable = normalized_source_value == normalized_required_value

            # Mettre à jour l'état du champ
            self._update_field_enabled_state(dependent_field, should_enable)

            logger.debug(f"Champ {dep_field_id} {'' if should_enable else 'dés'}activé (requis: {required_value}, actuel: {source_value})")

    def _update_dynamic_options_dependencies(self, source_field_id: str, source_unique_id: str, source_field: Widget) -> None:
        """
        Met à jour les options dynamiques des champs qui dépendent du champ source.

        Args:
            source_field_id: Identifiant du champ source
            source_unique_id: Identifiant unique du champ source
            source_field: Widget du champ source
        """
        # Utiliser les dictionnaires miroirs pour une recherche directe
        dependent_fields = []

        # Chercher dans le dictionnaire miroir avec l'ID du champ
        if source_field_id in self.mirror_dynamic_options:
            dependent_fields.extend(self.mirror_dynamic_options[source_field_id])

        # Chercher aussi avec l'ID unique si différent
        if source_unique_id != source_field_id and source_unique_id in self.mirror_dynamic_options:
            dependent_fields.extend(self.mirror_dynamic_options[source_unique_id])

        # Si aucun champ dépendant trouvé, sortir rapidement
        if not dependent_fields:
            return

        logger.debug(f"Mise à jour de {len(dependent_fields)} champs avec options dynamiques dépendant de {source_field_id}")

        # Préparer les valeurs des arguments pour les options dynamiques
        source_value = self._get_field_value(source_field)

        # Mettre à jour chaque champ dépendant
        for dep_field_id in dependent_fields:
            # Récupérer le champ dépendant
            dependent_field = self.fields_by_id.get(dep_field_id)
            if not dependent_field or not hasattr(dependent_field, 'update_dynamic_options'):
                continue

            # Vérifier si le champ est activé (ne pas mettre à jour les options des champs désactivés)
            if hasattr(dependent_field, 'disabled') and dependent_field.disabled:
                logger.debug(f"Champ {dep_field_id} désactivé, options non mises à jour")
                continue

            # Préparer les arguments pour la mise à jour des options
            update_kwargs = self._prepare_dynamic_options_args(dependent_field, dep_field_id, source_field_id, source_value)

            # Mettre à jour les options
            try:
                result = dependent_field.update_dynamic_options(**update_kwargs)
                logger.debug(f"Options mises à jour pour {dep_field_id}: {result}")

                # Vérifier s'il faut supprimer le champ (cas spécial: groupe de cases à cocher sans options)
                if not result and hasattr(dependent_field, 'field_config') and dependent_field.field_config.get('type') == 'checkbox_group':
                    logger.debug(f"Le champ {dep_field_id} n'a plus d'options, planifié pour suppression")
                    self._fields_to_remove.add(dep_field_id)
            except Exception as e:
                logger.error(f"Erreur lors de la mise à jour des options pour {dep_field_id}: {e}")

    def _prepare_dynamic_options_args(self, field: Widget, field_id: str, source_field_id: str, source_value: Any) -> Dict[str, Any]:
        """
        Prépare les arguments pour la mise à jour des options dynamiques.

        Args:
            field: Champ dont les options doivent être mises à jour
            field_id: Identifiant du champ
            source_field_id: Identifiant du champ qui a déclenché la mise à jour
            source_value: Valeur du champ source

        Returns:
            Dict[str, Any]: Arguments à passer à update_dynamic_options
        """
        kwargs = {}

        # Si le champ n'est pas dans notre mapping d'options dynamiques, retourner un dict vide
        if field_id not in self.dynamic_options_map:
            return kwargs

        # Récupérer la configuration des options dynamiques
        dynamic_config = self.dynamic_options_map[field_id]

        # Parcourir tous les arguments définis
        for arg in dynamic_config.get('args', []):
            if 'field_id' in arg and 'param_name' in arg:
                dep_field_id = arg['field_id']
                param_name = arg['param_name']

                # Si c'est le champ source qui a déclenché la mise à jour, utiliser sa valeur
                if dep_field_id == source_field_id:
                    kwargs[param_name] = source_value
                # Sinon, chercher la valeur dans les champs existants
                elif dep_field_id in self.fields_by_id:
                    dep_field = self.fields_by_id[dep_field_id]
                    # Ne pas inclure les valeurs des champs désactivés
                    if not (hasattr(dep_field, 'disabled') and dep_field.disabled):
                        kwargs[param_name] = self._get_field_value(dep_field)

        return kwargs

    def _update_value_dependencies(self, source_field_id: str, source_unique_id: str, source_field: Widget) -> None:
        """
        Met à jour les valeurs des champs qui dépendent du champ source.

        Args:
            source_field_id: Identifiant du champ source
            source_unique_id: Identifiant unique du champ source
            source_field: Widget du champ source
        """
        # Utiliser les dictionnaires miroirs pour une recherche directe
        dependent_fields = []

        # Chercher dans le dictionnaire miroir avec l'ID du champ
        if source_field_id in self.mirror_value_deps:
            dependent_fields.extend(self.mirror_value_deps[source_field_id])

        # Chercher aussi avec l'ID unique si différent
        if source_unique_id != source_field_id and source_unique_id in self.mirror_value_deps:
            dependent_fields.extend(self.mirror_value_deps[source_unique_id])

        # Si aucun champ dépendant trouvé, sortir rapidement
        if not dependent_fields:
            return

        # Récupérer la valeur actuelle du champ source
        source_value = self._get_field_value(source_field)
        logger.debug(f"Mise à jour de {len(dependent_fields)} champs dont la valeur dépend de {source_field_id}={source_value}")

        # Mettre à jour chaque champ dépendant
        for dep_field_id in dependent_fields:
            # Récupérer le champ dépendant
            dependent_field = self.fields_by_id.get(dep_field_id)
            if not dependent_field:
                continue

            # Vérifier si le champ est désactivé
            if hasattr(dependent_field, 'disabled') and dependent_field.disabled:
                logger.debug(f"Champ {dep_field_id} désactivé, valeur non mise à jour")
                continue

            # Déterminer la nouvelle valeur selon le type de dépendance
            new_value = self._compute_dependent_value(dependent_field, source_value)

            # Mettre à jour la valeur
            if new_value is not None:
                success = self._update_field_value(dependent_field, new_value)
                logger.debug(f"Valeur mise à jour pour {dep_field_id}: {new_value} (succès: {success})")

    def _compute_dependent_value(self, field: Widget, source_value: Any) -> Any:
        """
        Calcule la nouvelle valeur d'un champ dépendant.

        Args:
            field: Champ dont la valeur doit être calculée
            source_value: Valeur du champ source

        Returns:
            Any: Nouvelle valeur calculée ou None si pas de calcul possible
        """
                # Vérifier si le champ a un mapping de valeurs
        if hasattr(field, 'field_config') and 'values' in field.field_config:
            values_map = field.field_config['values']
            if source_value in values_map:
                return values_map[source_value]

        # Si le champ a une méthode pour calculer sa valeur basée sur une source
        if hasattr(field, '_get_default_value'):
            try:
                return field._get_default_value(source_value)
            except TypeError:
                # Si la méthode ne prend pas d'argument source_value
                pass

        # Par défaut, utiliser la source directement
        return source_value

    def _update_field_enabled_state(self, field: Widget, enabled: bool) -> None:
        """
        Met à jour l'état activé/désactivé d'un champ.

        Args:
            field: Champ à mettre à jour
            enabled: True pour activer, False pour désactiver
        """
        # Vérifier si l'état change réellement
        current_state = not (hasattr(field, 'disabled') and field.disabled)
        if current_state == enabled:
            return

        # Cas spécial: Si le champ a une méthode set_disabled
        if hasattr(field, 'set_disabled'):
            field.set_disabled(not enabled)
            logger.debug(f"État du champ {field.field_id} mis à jour via set_disabled: enabled={enabled}")
            return

                    # Cas général: Mettre à jour directement les attributs
        field.disabled = not enabled

        if enabled:
            field.remove_class('disabled')
            # Réactiver les widgets internes
            self._enable_field_widgets(field)
            # Restaurer la valeur sauvegardée si disponible
            self._restore_field_value(field)
        else:
            field.add_class('disabled')
            # Sauvegarder la valeur actuelle si ce n'est pas déjà fait
            if not hasattr(field, '_saved_value'):
                field._saved_value = self._get_field_value(field)
            # Désactiver les widgets internes
            self._disable_field_widgets(field)

            # Vérifier s'il faut supprimer le champ
            if hasattr(field, 'dependencies') and field.dependencies['enabled_if']:
                remove_if_disabled = field.dependencies['enabled_if'].get('remove_if_disabled', False)
                if remove_if_disabled:
                    self._fields_to_remove.add(field.field_id)

        logger.debug(f"État du champ {field.field_id} mis à jour: enabled={enabled}")

    def _enable_field_widgets(self, field: Widget) -> None:
        """
        Active tous les widgets internes d'un champ.

        Args:
            field: Champ dont les widgets doivent être activés
        """
        # Activer le widget input
        if hasattr(field, 'input'):
            field.input.disabled = False
            field.input.remove_class('disabled')

        # Activer le widget select
        if hasattr(field, 'select'):
            field.select.disabled = False
            field.select.remove_class('disabled')

        # Activer le widget checkbox
        if hasattr(field, 'checkbox'):
            field.checkbox.disabled = False
            field.checkbox.remove_class('disabled')

        # Activer le bouton browse des champs de répertoire
        if hasattr(field, '_browse_button'):
            field._browse_button.disabled = False
            field._browse_button.remove_class('disabled')

    def _disable_field_widgets(self, field: Widget) -> None:
        """
        Désactive tous les widgets internes d'un champ.

        Args:
            field: Champ dont les widgets doivent être désactivés
        """
        # Désactiver le widget input
        if hasattr(field, 'input'):
            field.input.disabled = True
            field.input.add_class('disabled')

        # Désactiver le widget select
        if hasattr(field, 'select'):
            field.select.disabled = True
            field.select.add_class('disabled')

        # Désactiver le widget checkbox
        if hasattr(field, 'checkbox'):
            field.checkbox.disabled = True
            field.checkbox.add_class('disabled')

        # Désactiver le bouton browse des champs de répertoire
        if hasattr(field, '_browse_button'):
            field._browse_button.disabled = True
            field._browse_button.add_class('disabled')

    def _restore_field_value(self, field: Widget) -> None:
        """
        Restaure la valeur sauvegardée d'un champ désactivé.

        Args:
            field: Champ dont la valeur doit être restaurée
        """
        # Vérifier si une valeur a été sauvegardée
        if not hasattr(field, '_saved_value'):
            return

        saved_value = field._saved_value

        # Utiliser set_value si disponible
        if hasattr(field, 'set_value'):
            field.set_value(saved_value, update_dependencies=False)
            logger.debug(f"Valeur restaurée pour {field.field_id}: {saved_value}")
        elif hasattr(field, 'value'):
            # Sinon, mettre à jour directement la valeur et le widget
            field.value = saved_value
            self._update_field_widget(field, saved_value)
            logger.debug(f"Valeur restaurée pour {field.field_id} via attribut value: {saved_value}")

        # Supprimer la valeur sauvegardée après restauration
        delattr(field, '_saved_value')

    def _get_field_value(self, field: Widget) -> Any:
        """
        Récupère la valeur d'un champ de manière sécurisée.

        Args:
            field: Champ dont il faut récupérer la valeur

        Returns:
            Any: Valeur du champ ou None en cas d'erreur
        """
        try:
            if hasattr(field, 'get_value'):
                return field.get_value()
            elif hasattr(field, 'value'):
                return field.value
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la valeur du champ: {e}")
            return None