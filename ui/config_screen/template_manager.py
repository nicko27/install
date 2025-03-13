"""
Gestionnaire centralisé des templates de configuration.
Gère le chargement, la validation et l'application des templates.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from ruamel.yaml import YAML
from logging import getLogger

yaml = YAML()
logger = getLogger('template_manager')

class TemplateManager:
    """Gestionnaire centralisé des templates"""

    def __init__(self):
        """Initialise le gestionnaire de templates"""
        self.templates_dir = self._get_templates_dir()
        self.schema = self._load_schema()
        self.templates: Dict[str, Dict[str, Any]] = {}
        logger.debug("Gestionnaire de templates initialisé")
        
    def _get_templates_dir(self) -> Path:
        """Récupère le chemin du dossier racine des templates"""
        templates_dir = Path(__file__).parent.parent.parent / 'templates'
        logger.debug(f"Templates directory: {templates_dir}")
        return templates_dir
        
    def _load_schema(self) -> dict:
        """Charge le schéma de validation des templates"""
        schema_file = self.templates_dir / 'template_schema.yml'
        try:
            if schema_file.exists():
                with open(schema_file, 'r', encoding='utf-8') as f:
                    return yaml.load(f)
        except Exception as e:
            logger.error(f"Erreur lors du chargement du schéma: {e}")
        return {}

    def get_plugin_templates(self, plugin_name: str) -> Dict[str, dict]:
        """
        Récupère tous les templates disponibles pour un plugin.

        Args:
            plugin_name: Nom du plugin

        Returns:
            Dictionnaire des templates disponibles
        """
        templates_dir = self.templates_dir / plugin_name
        templates = {}

        if not templates_dir.exists():
            logger.debug(f"Aucun dossier de templates trouvé pour {plugin_name}")
            return templates

        for template_file in templates_dir.glob('*.yml'):
            if template_file.name == 'template_schema.yml':
                continue

            try:
                with open(template_file, 'r', encoding='utf-8') as f:
                    template_data = yaml.load(f)
                    if self._validate_template(template_data):
                        templates[template_file.stem] = template_data
                        logger.debug(f"Template chargé : {template_file.name} pour {plugin_name}")
                    else:
                        logger.warning(f"Template invalide ignoré : {template_file.name}")
            except Exception as e:
                logger.error(f"Erreur lors du chargement du template {template_file} : {e}")

        return templates

    def _validate_template(self, template: dict) -> bool:
        """
        Valide un template selon le schéma.

        Args:
            template: Données du template à valider

        Returns:
            True si le template est valide
        """
        if not isinstance(template, dict):
            logger.warning("Le template doit être un dictionnaire")
            return False

        # Vérifier les champs requis
        required_fields = self.schema.get('required', ['name', 'description', 'variables'])
        for field in required_fields:
            if field not in template:
                logger.warning(f"Champ requis manquant : {field}")
                return False

        # Vérifier le format des variables
        if not isinstance(template['variables'], dict):
            logger.warning("Le champ 'variables' doit être un dictionnaire")
            return False

        logger.debug(f"Template validé avec succès : {template.get('name')}")
        return True

    def get_default_template(self, plugin_name: str) -> Optional[dict]:
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

    def get_template_names(self, plugin_name: str) -> List[str]:
        """
        Liste les noms des templates disponibles pour un plugin.

        Args:
            plugin_name: Nom du plugin

        Returns:
            Liste des noms de templates
        """
        names = list(self.get_plugin_templates(plugin_name).keys())
        logger.debug(f"Templates disponibles pour {plugin_name} : {names}")
        return names

    def get_template_description(self, plugin_name: str, template_name: str) -> str:
        """
        Récupère la description d'un template.

        Args:
            plugin_name: Nom du plugin
            template_name: Nom du template

        Returns:
            Description du template ou chaîne vide
        """
        templates = self.get_plugin_templates(plugin_name)
        template = templates.get(template_name, {})
        description = template.get('description', '')
        logger.debug(f"Description du template pour {plugin_name}/{template_name} : {description}")
        return description

    def get_template_variables(self, plugin_name: str, template_name: str) -> Optional[dict]:
        """
        Récupère les variables d'un template.

        Args:
            plugin_name: Nom du plugin
            template_name: Nom du template

        Returns:
            Variables du template ou None
        """
        templates = self.get_plugin_templates(plugin_name)
        template = templates.get(template_name)
        if template:
            variables = template['variables']
            logger.debug(f"Variables récupérées pour {plugin_name}/{template_name} : {list(variables.keys())}")
            return variables
        logger.debug(f"Aucune variable trouvée pour {plugin_name}/{template_name}")
        return None
