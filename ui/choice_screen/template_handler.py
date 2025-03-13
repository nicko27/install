"""
Gestionnaire de templates pour l'écran de sélection.
Gère le chargement et la validation des templates de plugins.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
from ruamel.yaml import YAML
from logging import getLogger

logger = getLogger('template_handler')
yaml = YAML()

class TemplateHandler:
    """Gestionnaire de templates pour l'écran de sélection"""

    def __init__(self):
        """Initialise le gestionnaire de templates"""
        self.templates_dir = Path('templates')
        self.schema_file = self.templates_dir / 'template_schema.yml'
        logger.debug(f"Dossier des templates : {self.templates_dir}")
        logger.debug(f"Fichier de schéma : {self.schema_file}")

    def get_plugin_templates(self, plugin_name: str) -> Dict[str, Any]:
        """
        Récupère tous les templates disponibles pour un plugin.
        
        Args:
            plugin_name: Nom du plugin
            
        Returns:
            Dictionnaire des templates disponibles
        """
        templates = {}
        plugin_templates_dir = self.templates_dir / plugin_name

        if not plugin_templates_dir.exists():
            logger.debug(f"Aucun dossier de templates trouvé pour {plugin_name}")
            return templates

        try:
            # Charger le schéma de validation si disponible
            schema = None
            if self.schema_file.exists():
                with open(self.schema_file, 'r', encoding='utf-8') as f:
                    schema = yaml.load(f)
                    logger.debug("Schéma de validation chargé")

            # Charger les templates du plugin
            for template_file in plugin_templates_dir.glob('*.yml'):
                try:
                    with open(template_file, 'r', encoding='utf-8') as f:
                        template_data = yaml.load(f)
                        if self._validate_template(template_data, schema):
                            templates[template_file.stem] = {
                                'name': template_data.get('name', template_file.stem),
                                'description': template_data.get('description', ''),
                                'variables': template_data.get('variables', {}),
                                'conditions': template_data.get('conditions', []),
                                'messages': template_data.get('messages', {}),
                                'file_name': template_file.name
                            }
                            logger.debug(f"Template chargé : {template_file.name}")
                        else:
                            logger.warning(f"Template invalide ignoré : {template_file.name}")
                except Exception as e:
                    logger.error(f"Erreur lors du chargement du template {template_file.name} : {e}")
        except Exception as e:
            logger.error(f"Erreur lors du chargement des templates pour {plugin_name} : {e}")

        return templates

    def _validate_template(self, template: dict, schema: Optional[dict] = None) -> bool:
        """
        Valide un template selon le schéma.
        
        Args:
            template: Données du template à valider
            schema: Schéma de validation optionnel
            
        Returns:
            True si le template est valide
        """
        if not isinstance(template, dict):
            logger.warning("Le template doit être un dictionnaire")
            return False

        # Validation de base
        required_fields = ['name', 'description', 'variables']
        for field in required_fields:
            if field not in template:
                logger.warning(f"Champ requis manquant : {field}")
                return False

        if not isinstance(template['variables'], dict):
            logger.warning("Le champ 'variables' doit être un dictionnaire")
            return False

        # Validation des conditions
        if 'conditions' in template:
            if not isinstance(template['conditions'], list):
                logger.warning("Les conditions doivent être une liste")
                return False

            for condition in template['conditions']:
                if not self._validate_condition(condition):
                    return False

        # Validation des messages
        if 'messages' in template:
            if not isinstance(template['messages'], dict):
                logger.warning("Le champ 'messages' doit être un dictionnaire")
                return False

            required_messages = ['success', 'error']
            for msg in required_messages:
                if msg not in template['messages']:
                    logger.warning(f"Message requis manquant : {msg}")
                    return False

        # Validation avec le schéma si disponible
        if schema:
            try:
                self._validate_against_schema(template, schema)
            except Exception as e:
                logger.warning(f"Erreur de validation avec le schéma : {e}")
                return False

        return True

    def _validate_condition(self, condition: dict) -> bool:
        """
        Valide une condition dans un template.
        
        Args:
            condition: Condition à valider
            
        Returns:
            True si la condition est valide
        """
        required_fields = ['variable', 'operator', 'value']
        for field in required_fields:
            if field not in condition:
                logger.warning(f"Champ requis manquant dans la condition : {field}")
                return False

        valid_operators = ['==', '!=', '>', '<', '>=', '<=', 'in', 'not in']
        if condition['operator'] not in valid_operators:
            logger.warning(f"Opérateur invalide : {condition['operator']}")
            return False

        return True

    def _validate_against_schema(self, template: dict, schema: dict) -> None:
        """
        Valide un template contre un schéma de validation.
        
        Args:
            template: Template à valider
            schema: Schéma de validation
            
        Raises:
            ValueError: Si le template ne respecte pas le schéma
        """
        if not schema or not isinstance(schema, dict):
            logger.warning("Schéma de validation invalide")
            raise ValueError("Schéma de validation invalide")

        # Vérification des champs requis
        required_fields = schema.get('required_fields', [])
        for field in required_fields:
            if field not in template:
                raise ValueError(f"Champ requis manquant : {field}")

        # Vérification des types de champs
        field_types = schema.get('field_types', {})
        for field, expected_type in field_types.items():
            if field in template:
                value = template[field]
                if expected_type == 'string' and not isinstance(value, str):
                    raise ValueError(f"Le champ {field} doit être une chaîne")
                elif expected_type == 'dict' and not isinstance(value, dict):
                    raise ValueError(f"Le champ {field} doit être un dictionnaire")
                elif expected_type == 'list' and not isinstance(value, list):
                    raise ValueError(f"Le champ {field} doit être une liste")
                elif expected_type == 'bool' and not isinstance(value, bool):
                    raise ValueError(f"Le champ {field} doit être un booléen")

        # Vérification des valeurs autorisées
        allowed_values = schema.get('allowed_values', {})
        for field, values in allowed_values.items():
            if field in template and template[field] not in values:
                raise ValueError(f"Valeur non autorisée pour {field}")

        # Vérification des formats spéciaux
        format_rules = schema.get('format_rules', {})
        for field, rule in format_rules.items():
            if field in template:
                value = template[field]
                if rule == 'version' and not self._is_valid_version(value):
                    raise ValueError(f"Format de version invalide pour {field}")
                elif rule == 'path' and not self._is_valid_path(value):
                    raise ValueError(f"Format de chemin invalide pour {field}")

        logger.debug("Validation du template contre le schéma réussie")

    def _is_valid_version(self, version: str) -> bool:
        """Vérifie si une version est valide (format X.Y.Z)"""
        try:
            parts = version.split('.')
            return len(parts) <= 3 and all(part.isdigit() for part in parts)
        except:
            return False

    def _is_valid_path(self, path: str) -> bool:
        """Vérifie si un chemin est valide"""
        try:
            return len(path) > 0 and '/' not in path and '..' not in path
        except:
            return False

    def get_default_template(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """
        Récupère le template par défaut d'un plugin.
        
        Args:
            plugin_name: Nom du plugin
            
        Returns:
            Template par défaut ou None
        """
        templates = self.get_plugin_templates(plugin_name)
        default = templates.get('default')
        if default:
            logger.debug(f"Template par défaut trouvé pour {plugin_name}")
        else:
            logger.debug(f"Aucun template par défaut trouvé pour {plugin_name}")
        return default

    def apply_template(self, plugin_name: str, template_name: str, config: dict) -> Dict[str, Any]:
        """
        Applique un template à une configuration de plugin.
        
        Args:
            plugin_name: Nom du plugin
            template_name: Nom du template à appliquer
            config: Configuration actuelle du plugin
            
        Returns:
            Configuration mise à jour avec le template
        """
        templates = self.get_plugin_templates(plugin_name)
        template = templates.get(template_name)
        
        if not template:
            logger.warning(f"Template non trouvé : {template_name}")
            return config

        # Fusionner les variables du template avec la configuration
        updated_config = config.copy()
        updated_config.update(template['variables'])
        
        logger.debug(f"Template {template_name} appliqué à {plugin_name}")
        return updated_config
