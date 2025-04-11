# ui/config_screen/config_container.py CORRIGÉ
from textual.app import ComposeResult
from textual.containers import VerticalGroup, HorizontalGroup
from textual.widgets import Label, Input, Select, Button, Checkbox
from textual.reactive import reactive
from textual.widget import Widget
from typing import Dict, List, Any, Optional, Set, Type, Union, Tuple
import re # Ajout de l'import re
import traceback
import logging

from .text_field import TextField
from .directory_field import DirectoryField
from .ip_field import IPField
from .checkbox_field import CheckboxField
from .select_field import SelectField
from .checkbox_group_field import CheckboxGroupField
from .password_field import PasswordField
from .config_field import ConfigField # Assurer l'import de ConfigField

from ..utils.logging import get_logger

logger = get_logger('config_container')

class ConfigContainer(VerticalGroup):
    """
    Conteneur de configuration qui gère les dépendances entre les champs.
    
    Cette classe sert de base pour tous les conteneurs de configuration
    et fournit des fonctionnalités pour analyser et gérer les dépendances
    entre les champs, mettre à jour les champs dépendants et gérer les états.
    """

    def __init__(self, source_id: str, instance_id: Optional[int] = None):
        """
        Initialise le conteneur de configuration.

        Args:
            source_id: ID de la source (plugin ou global)
            instance_id: ID d'instance optionnel
        """
        super().__init__()
        self.source_id = source_id
        self.instance_id = instance_id
        self.fields_by_id = {}
        self._field_dependencies = {}
        self._dependent_fields_map = {}
        self._plugin_dependencies = {}
        self._dependent_plugins_map = {}
        self._field_errors = {}
        self._is_updating_values = False
        
        logger.debug(f"Conteneur de configuration initialisé pour {source_id} (instance: {instance_id})")

    def _analyze_field_dependencies(self, config_fields: List[Dict[str, Any]]) -> None:
        """
        Analyse les dépendances entre les champs pour optimiser les mises à jour.
        Construction des mappings de dépendances bidirectionnels.

        Args:
            config_fields: Liste des configurations de champs
        """
        try:
            self._field_dependencies = {}
            self._dependent_fields_map = {}
            
            logger.debug(f"Analyse des dépendances pour {len(config_fields)} champs")

            for field_config in config_fields:
                field_base_id = field_config.get('id')
                if not field_base_id:
                    logger.warning(f"Champ sans ID trouvé dans la configuration, ignoré")
                    continue

                # Construire l'ID unique du champ
                field_unique_id = self._get_unique_field_id(field_base_id)
                logger.debug(f"Analyse des dépendances pour le champ {field_unique_id}")

                # Collecter les dépendances
                dependencies_base_ids = set()

                # 1. Dépendance enabled_if
                if 'enabled_if' in field_config and 'field' in field_config['enabled_if']:
                    dep_field_id = field_config['enabled_if']['field']
                    dependencies_base_ids.add(dep_field_id)
                    logger.debug(f"Dépendance 'enabled_if' trouvée: {dep_field_id}")

                # 2. Dépendance depends_on
                if 'depends_on' in field_config:
                    dep_field_id = field_config['depends_on']
                    dependencies_base_ids.add(dep_field_id)
                    logger.debug(f"Dépendance 'depends_on' trouvée: {dep_field_id}")

                # 3. Dépendances dynamiques
                for dynamic_key in ['dynamic_options', 'dynamic_default']:
                    if dynamic_key in field_config and 'args' in field_config[dynamic_key]:
                        for arg in field_config[dynamic_key]['args']:
                            if 'field' in arg:
                                dep_field_id = arg['field']
                                dependencies_base_ids.add(dep_field_id)
                                logger.debug(f"Dépendance dynamique trouvée ({dynamic_key}): {dep_field_id}")

                # Stocker les dépendances
                if dependencies_base_ids:
                    self._field_dependencies[field_unique_id] = dependencies_base_ids
                    logger.debug(f"Champ {field_unique_id} dépend de: {dependencies_base_ids}")

                    # Construire le mapping inverse
                    for dep_base_id in dependencies_base_ids:
                        dep_unique_id = self._get_unique_field_id(dep_base_id)
                        if dep_unique_id not in self._dependent_fields_map:
                            self._dependent_fields_map[dep_unique_id] = set()
                        self._dependent_fields_map[dep_unique_id].add(field_unique_id)
                        logger.debug(f"Champ {dep_unique_id} a pour dépendant: {field_unique_id}")
            
            logger.debug(f"Analyse des dépendances terminée: {len(self._field_dependencies)} champs avec dépendances, " + 
                        f"{len(self._dependent_fields_map)} champs sources")
                        
        except Exception as e:
            logger.error(f"Erreur lors de l'analyse des dépendances: {e}")
            logger.error(traceback.format_exc())
            # Réinitialiser les mappings en cas d'erreur
            self._field_dependencies = {}
            self._dependent_fields_map = {}

    def _get_unique_field_id(self, base_id: str) -> str:
        """
        Construit l'ID unique d'un champ en fonction de l'instance.
        
        Args:
            base_id: ID de base du champ
            
        Returns:
            str: ID unique du champ
        """
        if '.' in base_id:
            # Cas spécial: ID qualifié avec un plugin (format: plugin.field)
            plugin_id, field_id = base_id.split('.')
            if self.instance_id is not None:
                return f"{plugin_id}.{field_id}_{self.instance_id}"
            return base_id
        elif self.instance_id is not None:
            return f"{base_id}_{self.instance_id}"
        return base_id

    def update_dependent_fields(self, source_field: Any) -> None:
        """
        Met à jour tous les champs qui dépendent du champ source dont la valeur a changé.

        Args:
            source_field: Champ source dont la valeur a changé
        """
        if self._is_updating_values:
            logger.debug("Mise à jour récursive évitée dans update_dependent_fields")
            return
            
        try:
            self._is_updating_values = True
            
            if not hasattr(source_field, 'unique_id'):
                logger.warning("Champ source sans unique_id, impossible de mettre à jour les dépendants")
                return

            source_unique_id = source_field.unique_id
            logger.debug(f"Mise à jour des champs dépendants de {source_unique_id}")

            # Vérifier si le champ source a des dépendants
            if source_unique_id not in self._dependent_fields_map:
                logger.debug(f"Aucun champ dépendant pour {source_unique_id}")
                return

            # Parcourir tous les champs dépendants
            for dependent_unique_id in self._dependent_fields_map[source_unique_id]:
                dependent_field = self.fields_by_id.get(dependent_unique_id)
                if not dependent_field:
                    logger.warning(f"Champ dépendant {dependent_unique_id} non trouvé")
                    continue

                # Mettre à jour le champ dépendant
                self._update_dependent_field(dependent_field, source_field)
                
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour des champs dépendants: {e}")
            logger.error(traceback.format_exc())
        finally:
            self._is_updating_values = False

    def _update_dependent_field(self, dependent_field: Any, source_field: Any) -> None:
        """
        Met à jour un champ dépendant en gérant les différents types de dépendances.

        Args:
            dependent_field: Champ dépendant à mettre à jour
            source_field: Champ source dont la valeur a changé
        """
        try:
            dep_field_id = getattr(dependent_field, 'unique_id', 'unknown')
            src_field_id = getattr(source_field, 'unique_id', 'unknown')
            logger.debug(f"Mise à jour du champ dépendant: {dep_field_id} (source: {src_field_id})")

            # 1. Mise à jour de l'état d'activation
            if hasattr(dependent_field, 'enabled_if'):
                self._update_field_enabled_state(dependent_field)

            # 2. Mise à jour des options dynamiques
            if hasattr(dependent_field, 'dynamic_options'):
                self._update_field_dynamic_options(dependent_field)

            # 3. Mise à jour de la valeur dépendante
            if hasattr(dependent_field, 'depends_on'):
                self._update_field_dependent_value(dependent_field)
                
            logger.debug(f"Mise à jour du champ {dep_field_id} terminée")
            
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du champ dépendant {getattr(dependent_field, 'unique_id', 'unknown')}: {e}")
            logger.error(traceback.format_exc())

    def _update_field_enabled_state(self, field: ConfigField) -> None:
        """
        Met à jour l'état d'activation d'un champ en fonction de ses dépendances.

        Args:
            field: Champ à mettre à jour
        """
        if not hasattr(field, 'enabled_if') or not field.enabled_if:
            return

        try:
            enabled_config = field.enabled_if
            source_field_id = enabled_config.get('field')
            required_value = enabled_config.get('value')

            if not source_field_id:
                logger.warning(f"Champ {field.unique_id} a un enabled_if sans field")
                return

            # Trouver le champ source
            source_field = self._get_field_by_id(source_field_id)
            if not source_field:
                logger.warning(f"Champ source {source_field_id} non trouvé pour enabled_if de {field.unique_id}")
                self._toggle_field_state(field, False)  # Désactiver par sécurité
                return

            # Récupérer et normaliser les valeurs
            source_value = self._get_field_value(source_field)
            source_value_norm = self._normalize_value(source_value)
            required_value_norm = self._normalize_value(required_value)

            # Déterminer l'état
            should_enable = source_value_norm == required_value_norm
            logger.debug(f"État d'activation pour {field.unique_id}: {should_enable} ({source_value} == {required_value})")

            # Appliquer l'état
            self._toggle_field_state(field, should_enable)

            # Si le champ est désactivé, appliquer sa valeur par défaut
            if not should_enable and hasattr(field, 'field_config') and 'default' in field.field_config:
                default_value = field.field_config['default']
                logger.debug(f"Application de la valeur par défaut pour {field.unique_id}: {default_value}")
                if hasattr(field, 'set_value'):
                    field.set_value(default_value, update_dependencies=False)
                elif hasattr(field, 'value'):
                    field.value = default_value
                    self._update_field_widget(field, default_value)

        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'état d'activation pour {field.unique_id}: {e}")
            logger.error(traceback.format_exc())
            # En cas d'erreur, désactiver le champ par sécurité
            self._toggle_field_state(field, False)

    def _update_field_dynamic_options(self, field: ConfigField) -> None:
        """
        Met à jour les options dynamiques d'un champ.
        
        Args:
            field: Le champ à mettre à jour
        """
        if not hasattr(field, 'dynamic_options') or not field.dynamic_options:
            logger.debug(f"Champ {field.unique_id} n'a pas d'options dynamiques")
            return

        try:
            logger.debug(f"Mise à jour des options dynamiques pour {field.unique_id}")
            
            # Récupérer les options dynamiques
            if hasattr(field.dynamic_options, 'get_options'):
                options = field.dynamic_options.get_options()
                logger.debug(f"Options dynamiques obtenues: {options}")
                
                # Mettre à jour le champ
                if hasattr(field, 'update_options'):
                    field.update_options(options)
                    logger.debug(f"Options dynamiques appliquées au champ {field.unique_id}")
                else:
                    logger.warning(f"Champ {field.unique_id} n'a pas de méthode update_options")
            else:
                logger.warning(f"dynamic_options de {field.unique_id} n'a pas de méthode get_options")
                
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour des options dynamiques pour {field.unique_id}: {e}")
            logger.error(traceback.format_exc())
            self._show_error(f"Erreur lors de la mise à jour des options dynamiques : {str(e)}")

    def _update_field_dependent_value(self, field: ConfigField) -> None:
        """
        Met à jour la valeur d'un champ dépendant en fonction d'un autre champ.

        Args:
            field: Champ à mettre à jour
        """
        if not hasattr(field, 'depends_on') or not field.depends_on:
            return

        try:
            depends_on_id = field.depends_on
            logger.debug(f"Mise à jour de la valeur de {field.unique_id} dépendant de {depends_on_id}")

            # Trouver le champ source
            source_field = self._get_field_by_id(depends_on_id)
            if not source_field:
                logger.warning(f"Champ source {depends_on_id} non trouvé pour {field.unique_id}")
                return

            # Récupérer la valeur du champ source
            source_value = self._get_field_value(source_field)
            logger.debug(f"Valeur source pour {field.unique_id}: {source_value}")

            # Vérifier si le champ a un mapping de valeurs
            if hasattr(field, 'field_config') and 'values' in field.field_config:
                values_map = field.field_config['values']
                
                # Normaliser la valeur pour la recherche dans le mapping
                source_value_norm = self._normalize_value(source_value)
                
                # Chercher la valeur normalisée dans le mapping
                found_mapping = False
                for map_key, map_value in values_map.items():
                    if self._normalize_value(map_key) == source_value_norm:
                        new_value = map_value
                        logger.debug(f"Valeur mappée trouvée pour {field.unique_id}: {source_value} -> {new_value}")
                        
                        # Appliquer la nouvelle valeur
                        self._apply_value_to_field(field, new_value)
                        found_mapping = True
                        break
                        
                if not found_mapping:
                    logger.warning(f"Valeur {source_value} non trouvée dans le mapping pour {field.unique_id}")
                    if 'default' in field.field_config:
                        default_value = field.field_config['default']
                        logger.debug(f"Application de la valeur par défaut: {default_value}")
                        self._apply_value_to_field(field, default_value)
                    
            # Vérifier si le champ a une valeur par défaut dynamique
            elif hasattr(field, '_get_dynamic_default'):
                new_value = field._get_dynamic_default()
                if new_value is not None:
                    logger.debug(f"Valeur dynamique pour {field.unique_id}: {new_value}")
                    self._apply_value_to_field(field, new_value)
                else:
                    logger.debug(f"Pas de valeur dynamique pour {field.unique_id}")

        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de la valeur dépendante pour {field.unique_id}: {e}")
            logger.error(traceback.format_exc())

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
                
                # TODO: Implémentation spécifique pour accéder aux champs d'autres plugins
                # Cette fonctionnalité nécessite une référence à l'écran de configuration
                logger.debug(f"Recherche du champ {field_id} dans un autre plugin")
                return None
                
            # Cas 2: Champ dans notre conteneur
            unique_field_id = self._get_unique_field_id(field_id)
            field = self.fields_by_id.get(unique_field_id)
            
            if field:
                logger.debug(f"Champ {field_id} trouvé avec ID unique {unique_field_id}")
                return field
                
            # Cas 3: Chercher le champ sans instance ID
            if field_id in self.fields_by_id:
                logger.debug(f"Champ {field_id} trouvé directement")
                return self.fields_by_id[field_id]
                
            # Cas 4: Chercher avec l'ID de base (cas où le champ a été enregistré avec son ID unique)
            for registered_id, registered_field in self.fields_by_id.items():
                if hasattr(registered_field, 'field_id') and registered_field.field_id == field_id:
                    logger.debug(f"Champ {field_id} trouvé via field_id")
                    return registered_field
            
            logger.warning(f"Champ {field_id} non trouvé")
            return None
            
        except Exception as e:
            logger.error(f"Erreur lors de la recherche du champ {field_id}: {e}")
            return None

    def _get_field_value(self, field: Any) -> Any:
        """
        Récupère la valeur d'un champ de manière sécurisée.

        Args:
            field: Champ dont on veut la valeur

        Returns:
            Any: Valeur du champ
        """
        if field is None:
            return None
            
        try:
            # Utiliser get_value si disponible
            if hasattr(field, 'get_value'):
                return field.get_value()
                
            # Fallback sur l'attribut value
            if hasattr(field, 'value'):
                return field.value
                
            return None
            
        except Exception as e:
            field_id = getattr(field, 'unique_id', str(field))
            logger.error(f"Erreur lors de la récupération de la valeur pour {field_id}: {e}")
            return None

    def _toggle_field_state(self, field: Any, enable: bool) -> None:
        """
        Active ou désactive un champ.

        Args:
            field: Champ à modifier
            enable: True pour activer, False pour désactiver
        """
        if field is None:
            logger.warning("Tentative de modifier l'état d'un champ None")
            return
            
        try:
            # Utiliser la méthode interne du champ si disponible
            if hasattr(field, '_toggle_field_state'):
                field._toggle_field_state(enable)
                logger.debug(f"État du champ {field.unique_id} modifié via sa méthode interne: {enable}")
                return
            
            # Fallback: modification directe des attributs
            field.disabled = not enable
            if enable:
                field.remove_class('disabled')
            else:
                field.add_class('disabled')

            # Désactiver aussi les widgets internes
            self._toggle_internal_widgets(field, enable)
            
            logger.debug(f"État du champ {getattr(field, 'unique_id', 'unknown')} modifié: {enable}")

        except Exception as e:
            field_id = getattr(field, 'unique_id', str(field))
            logger.error(f"Erreur lors de la modification de l'état du champ {field_id}: {e}")

    def _toggle_internal_widgets(self, field: Any, enable: bool) -> None:
        """
        Active ou désactive les widgets internes d'un champ.

        Args:
            field: Champ à modifier
            enable: True pour activer, False pour désactiver
        """
        if field is None:
            return
            
        try:
            # Utiliser la méthode interne du champ si disponible
            if hasattr(field, '_toggle_internal_widgets'):
                field._toggle_internal_widgets(enable)
                return
                
            # Fallback: modification directe des widgets
            widgets_to_toggle = []
            
            if hasattr(field, 'input') and field.input:
                widgets_to_toggle.append(field.input)
            if hasattr(field, 'select') and field.select:
                widgets_to_toggle.append(field.select)
            if hasattr(field, 'checkbox') and field.checkbox:
                widgets_to_toggle.append(field.checkbox)
                
            if hasattr(field, 'checkboxes') and isinstance(field.checkboxes, dict):
                for widget in field.checkboxes.values():
                    if widget:
                        widgets_to_toggle.append(widget)
                        
            if hasattr(field, '_browse_button') and field._browse_button:
                widgets_to_toggle.append(field._browse_button)

            for widget in widgets_to_toggle:
                widget.disabled = not enable
                if enable:
                    widget.remove_class('disabled')
                else:
                    widget.add_class('disabled')

        except Exception as e:
            field_id = getattr(field, 'unique_id', str(field))
            logger.error(f"Erreur lors de la modification des widgets de {field_id}: {e}")

    def _update_field_widget(self, field: Any, value: Any) -> None:
        """
        Met à jour le widget d'un champ avec une nouvelle valeur.

        Args:
            field: Le champ à mettre à jour
            value: La nouvelle valeur à appliquer
        """
        if field is None:
            return
            
        try:
            # Utiliser la méthode interne du champ si disponible
            if hasattr(field, '_update_field_widget'):
                field._update_field_widget(field, value)
                return
                
            # Fallback: mise à jour directe des widgets
            field_id = getattr(field, 'unique_id', getattr(field, 'field_id', 'unknown'))
            logger.debug(f"Mise à jour du widget pour {field_id} avec valeur: {value}")
            
            # Mise à jour selon le type de widget
            if hasattr(field, 'input') and field.input:
                field.input.value = str(value) if value is not None else ""
            elif hasattr(field, 'select') and field.select:
                field.select.value = str(value) if value is not None else ""
            elif hasattr(field, 'checkbox') and field.checkbox:
                field.checkbox.value = bool(value)
                
        except Exception as e:
            field_id = getattr(field, 'unique_id', str(field))
            logger.error(f"Erreur lors de la mise à jour du widget pour {field_id}: {e}")

    def _apply_value_to_field(self, field: Any, value: Any) -> bool:
        """
        Applique une valeur à un champ en utilisant la méthode appropriée.

        Args:
            field: Le champ à mettre à jour
            value: La valeur à appliquer

        Returns:
            bool: True si la valeur a été appliquée avec succès
        """
        if field is None:
            return False
            
        try:
            # Utiliser la méthode interne du champ si disponible
            if hasattr(field, '_apply_value_to_field'):
                return field._apply_value_to_field(value)
                
            # Méthode set_value si disponible
            if hasattr(field, 'set_value'):
                return field.set_value(value, update_dependencies=False)
                
            # Fallback: modifier directement value et mettre à jour le widget
            if hasattr(field, 'value'):
                field.value = value
                self._update_field_widget(field, value)
                return True
                
            logger.warning(f"Impossible d'appliquer la valeur au champ {getattr(field, 'unique_id', 'unknown')}")
            return False
            
        except Exception as e:
            field_id = getattr(field, 'unique_id', str(field))
            logger.error(f"Erreur lors de l'application de la valeur au champ {field_id}: {e}")
            return False

    def _normalize_value(self, value: Any) -> Any:
        """
        Normalise une valeur pour les comparaisons.
        
        Args:
            value: Valeur à normaliser
            
        Returns:
            Any: Valeur normalisée
        """
        # Pour les booléens, normaliser vers True/False
        if isinstance(value, str) and value.lower() in ('true', 'false', 'yes', 'no', '1', '0'):
            return value.lower() in ('true', 'yes', '1')
            
        # Pour les nombres sous forme de chaîne
        if isinstance(value, str):
            try:
                if '.' in value:
                    return float(value)
                else:
                    return int(value)
            except (ValueError, TypeError):
                pass
                
        # Valeur par défaut: retourner telle quelle
        return value

    def _show_error(self, message: str) -> None:
        """
        Affiche un message d'erreur à l'utilisateur.
        
        Args:
            message: Message d'erreur à afficher
        """
        logger.error(message)
        # L'implémentation spécifique dépend de la façon dont vous souhaitez notifier l'utilisateur
        # Par exemple:
        # self.app.notify(message, severity="error")
        
    def update_all_dependencies(self) -> None:
        """
        Met à jour toutes les dépendances entre les champs.
        Utile après le chargement initial ou après des modifications massives.
        """
        if self._is_updating_values:
            return
            
        try:
            logger.debug("Mise à jour de toutes les dépendances")
            self._is_updating_values = True
            
            # Parcourir tous les champs avec des dépendants
            for source_id in list(self._dependent_fields_map.keys()):
                source_field = self.fields_by_id.get(source_id)
                if source_field:
                    # Pour chaque champ dépendant du champ source
                    for dependent_id in self._dependent_fields_map[source_id]:
                        dependent_field = self.fields_by_id.get(dependent_id)
                        if dependent_field:
                            self._update_dependent_field(dependent_field, source_field)
                            
            logger.debug("Mise à jour de toutes les dépendances terminée")
            
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de toutes les dépendances: {e}")
            logger.error(traceback.format_exc())
        finally:
            self._is_updating_values = False
            
    def register_field(self, field: ConfigField) -> None:
        """
        Enregistre un champ dans le conteneur pour la gestion des dépendances.
        
        Args:
            field: Champ à enregistrer
        """
        if not field or not hasattr(field, 'unique_id'):
            logger.warning("Tentative d'enregistrer un champ invalide")
            return
            
        try:
            unique_id = field.unique_id
            logger.debug(f"Enregistrement du champ {unique_id}")
            
            # Ajouter au dictionnaire des champs
            self.fields_by_id[unique_id] = field
            
            # Mettre à jour les dépendances si nécessaire
            if hasattr(field, 'depends_on') or hasattr(field, 'enabled_if'):
                logger.debug(f"Le champ {unique_id} a des dépendances, mise à jour de son état initial")
                if hasattr(field, '_check_initial_state'):
                    field._check_initial_state()
                    
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement du champ: {e}")
