"""
Gestionnaire de séquences avec support pour l'exécution conditionnelle.
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
import os
from ruamel.yaml import YAML
from logging import getLogger

yaml = YAML()
logger = getLogger('sequence_manager')

class SequenceManager:
    """Gestionnaire de séquences d'exécution de plugins"""

    def __init__(self):
        """Initialise le gestionnaire de séquences"""
        self.sequences_dir = self._get_sequences_dir()
        logger.debug("Dossier des séquences configuré : %s", self.sequences_dir)
        
        self.schema = self._load_schema()
        logger.debug("Schéma de validation chargé")
        
        self.sequences: Dict[str, Dict[str, Any]] = {}
        self.environment: Dict[str, Any] = {}
        logger.debug("Gestionnaire de séquences initialisé")

    def _get_sequences_dir(self) -> Path:
        """Récupère le chemin du dossier des séquences"""
        sequences_dir = Path(__file__).parent.parent.parent / 'sequences'
        logger.debug(f"Dossier des séquences : {sequences_dir}")
        return sequences_dir

    def _load_schema(self) -> dict:
        """Charge le schéma de validation des séquences"""
        schema_file = self.sequences_dir / 'sequence_schema.yml'
        try:
            if schema_file.exists():
                with open(schema_file, 'r', encoding='utf-8') as f:
                    return yaml.load(f)
        except Exception as e:
            logger.error(f"Erreur lors du chargement du schéma : {e}")
        return {}

    def load_sequence(self, sequence_name: str) -> Optional[dict]:
        """
        Charge une séquence depuis un fichier.

        Args:
            sequence_name: Nom de la séquence

        Returns:
            Données de la séquence ou None
        """
        sequence_file = self.sequences_dir / f"{sequence_name}.yml"
        try:
            if sequence_file.exists():
                with open(sequence_file, 'r', encoding='utf-8') as f:
                    sequence = yaml.load(f)
                    if self._validate_sequence(sequence):
                        logger.debug(f"Séquence chargée : {sequence_name}")
                        return sequence
                    logger.warning(f"Séquence invalide : {sequence_name}")
            else:
                logger.warning(f"Fichier de séquence non trouvé : {sequence_name}")
        except Exception as e:
            logger.error(f"Erreur lors du chargement de la séquence {sequence_name} : {e}")
        return None

    def _validate_sequence(self, sequence: dict) -> bool:
        """
        Valide une séquence selon le schéma.

        Args:
            sequence: Données de la séquence à valider

        Returns:
            True si la séquence est valide
        """
        if not isinstance(sequence, dict):
            logger.warning("La séquence doit être un dictionnaire")
            return False

        required_fields = ['name', 'description', 'steps']
        for field in required_fields:
            if field not in sequence:
                logger.warning(f"Champ requis manquant : {field}")
                return False

        if not isinstance(sequence['steps'], list):
            logger.warning("Format de séquence invalide : les étapes doivent être une liste")
            return False

        for step in sequence['steps']:
            if not self._validate_step(step):
                return False

        return True

    def _validate_step(self, step: dict) -> bool:
        """
        Valide une étape de séquence.

        Args:
            step: Données de l'étape à valider

        Returns:
            True si l'étape est valide
        """
        required_fields = ['plugin']
        for field in required_fields:
            if field not in step:
                logger.warning(f"Champ requis manquant dans l'étape : {field}")
                return False

        # Validation des conditions
        if 'conditions' in step:
            if not isinstance(step['conditions'], list):
                logger.warning("Les conditions doivent être une liste")
                return False
            for condition in step['conditions']:
                if not self._validate_condition(condition):
                    return False

        return True

    def _validate_condition(self, condition: dict) -> bool:
        """
        Valide une condition.

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

    def evaluate_conditions(self, conditions: List[dict]) -> bool:
        """
        Évalue une liste de conditions.

        Args:
            conditions: Liste des conditions à évaluer

        Returns:
            True si toutes les conditions sont satisfaites
        """
        for condition in conditions:
            variable = condition['variable']
            operator = condition['operator']
            expected_value = condition['value']

            # Récupérer la valeur réelle
            actual_value = self.environment.get(variable)
            if actual_value is None:
                logger.warning(f"Variable d'environnement non trouvée : {variable}")
                return False

            # Évaluer la condition
            result = self._evaluate_condition(actual_value, operator, expected_value)
            if not result:
                logger.debug(
                    f"Condition non satisfaite pour {variable} : "
                    f"valeur actuelle = {actual_value}, "
                    f"attendue {operator} {expected_value}"
                )
                return False
            logger.debug(
                f"Condition satisfaite pour {variable} : "
                f"valeur actuelle = {actual_value} {operator} {expected_value}"
            )

        return True

    def _evaluate_condition(self, actual: Any, operator: str, expected: Any) -> bool:
        """
        Évalue une condition individuelle.

        Args:
            actual: Valeur réelle
            operator: Opérateur de comparaison
            expected: Valeur attendue

        Returns:
            True si la condition est satisfaite
        """
        try:
            if operator == '==':
                return actual == expected
            elif operator == '!=':
                return actual != expected
            elif operator == '>':
                return actual > expected
            elif operator == '<':
                return actual < expected
            elif operator == '>=':
                return actual >= expected
            elif operator == '<=':
                return actual <= expected
            elif operator == 'in':
                return actual in expected
            elif operator == 'not in':
                return actual not in expected
            else:
                logger.error(f"Opérateur non supporté : {operator}")
                return False
        except TypeError as e:
            logger.error(
                f"Types incompatibles pour la comparaison : "
                f"valeur={type(actual)}, attendu={type(expected)}, "
                f"erreur={str(e)}"
            )
            return False
        except Exception as e:
            logger.error(
                f"Erreur inattendue lors de l'évaluation : "
                f"opérateur={operator}, valeur={actual}, attendu={expected}, "
                f"erreur={str(e)}"
            )
            return False

    def update_environment(self, plugin_name: str, result: Any, export_result: Optional[str] = None):
        """
        Met à jour l'environnement avec le résultat d'un plugin.

        Args:
            plugin_name: Nom du plugin
            result: Résultat de l'exécution
            export_result: Nom de la variable d'export (optionnel)
        """
        # Utiliser le nom par défaut si non spécifié
        var_name = export_result or f"{plugin_name.upper()}_STATUS"
        self.environment[var_name] = result
        logger.debug(
            f"Résultat de {plugin_name} exporté : "
            f"{var_name} = {result} "
            f"({'nom personnalisé' if export_result else 'nom par défaut'})"
        )

    def should_continue(self, step: dict, stop_on_first_fail: bool) -> bool:
        """
        Détermine si l'exécution doit continuer après une étape.

        Args:
            step: Étape courante
            stop_on_first_fail: Option globale d'arrêt sur erreur

        Returns:
            True si l'exécution doit continuer
        """
        # Vérifier les conditions si présentes
        if 'conditions' in step:
            if not self.evaluate_conditions(step['conditions']):
                logger.debug("Conditions non satisfaites, étape ignorée")
                return True  # Continuer avec l'étape suivante

        # Vérifier si l'étape a un résultat
        plugin_name = step['plugin']
        result_var = step.get('export_result', f"{plugin_name.upper()}_STATUS")
        result = self.environment.get(result_var)

        # Si pas de résultat, continuer par défaut
        if result is None:
            return True

        # Si stop_on_first_fail est activé et qu'il y a une erreur
        if stop_on_first_fail and not result:
            logger.warning(
                f"Arrêt de la séquence suite à l'échec de {plugin_name} "
                f"(option stop_on_first_fail activée)"
            )
            return False
        elif not result:
            logger.warning(
                f"Échec de l'étape {plugin_name} mais la séquence continue "
                f"(option stop_on_first_fail désactivée)"
            )
            return True

        return True
