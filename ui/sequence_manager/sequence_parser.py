"""
Parseur pour les fichiers de séquence et gestionnaire de conditions
"""

import os
import re
import yaml
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Union

from .condition_evaluator import ConditionEvaluator
from ..utils.logging import get_logger

# Configuration du logger
logger = get_logger('pcutils.sequence_parser')

class SequenceParser:
    """
    Classe responsable du chargement et de la validation des fichiers de séquence
    """
    
    def __init__(self, sequences_dir: str = "sequences"):
        """
        Initialise le parseur de séquences
        
        Args:
            sequences_dir: Chemin du répertoire contenant les séquences
        """
        self.sequences_dir = sequences_dir
        self._variables = {}  # Variables d'environnement et résultats
        self.condition_evaluator = ConditionEvaluator()
        
    def load_sequence(self, sequence_path: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Charge et valide un fichier de séquence
        
        Args:
            sequence_path: Chemin vers le fichier de séquence
            
        Returns:
            Tuple avec (succès, données ou message d'erreur)
        """
        try:
            # Vérifier que le fichier existe
            if not os.path.exists(sequence_path):
                return False, f"Le fichier de séquence '{sequence_path}' n'existe pas"
            
            # Charger le YAML
            with open(sequence_path, 'r') as f:
                sequence_data = yaml.safe_load(f)
            
            # Valider le contenu minimal
            if not isinstance(sequence_data, dict):
                return False, "Le fichier de séquence n'est pas un document YAML valide"
            
            if 'name' not in sequence_data:
                return False, "Le fichier de séquence doit définir un nom"
                
            if 'sequences' not in sequence_data or not isinstance(sequence_data['sequences'], list):
                return False, "Le fichier de séquence doit contenir une liste d'étapes"
                
            # Valider chaque étape
            for idx, step in enumerate(sequence_data['sequences']):
                if not isinstance(step, dict):
                    return False, f"L'étape {idx+1} n'est pas un objet valide"
                
                if 'id' not in step:
                    return False, f"L'étape {idx+1} n'a pas d'identifiant"
                
                if 'plugin' not in step:
                    return False, f"L'étape {step['id']} n'a pas de plugin spécifié"
                
                if 'name' not in step:
                    # Utiliser l'ID comme nom par défaut
                    step['name'] = step['id']
                
                if 'config' not in step or not isinstance(step['config'], dict):
                    step['config'] = {}  # Configuration vide par défaut
            
            # Normaliser les options avec des valeurs par défaut
            if 'options' not in sequence_data or not isinstance(sequence_data['options'], dict):
                sequence_data['options'] = {}
            
            options = sequence_data['options']
            options.setdefault('stop_on_failure', False)
            options.setdefault('stop_on_condition_fail', False)
            
            return True, sequence_data
            
        except yaml.YAMLError as e:
            return False, f"Erreur de syntaxe YAML: {str(e)}"
        except Exception as e:
            return False, f"Erreur lors du chargement de la séquence: {str(e)}"
    
    def discover_sequences(self) -> List[Dict[str, Any]]:
        """
        Découvre tous les fichiers de séquence disponibles dans le répertoire
        
        Returns:
            Liste des séquences découvertes
        """
        sequences = []
        
        if not os.path.exists(self.sequences_dir):
            logger.warning(f"Le répertoire de séquences '{self.sequences_dir}' n'existe pas")
            return sequences
        
        for filename in os.listdir(self.sequences_dir):
            if filename.endswith('.yml') or filename.endswith('.yaml'):
                filepath = os.path.join(self.sequences_dir, filename)
                success, data = self.load_sequence(filepath)
                
                if success:
                    # Ajouter le chemin à la configuration
                    data['filepath'] = filepath
                    sequences.append(data)
                else:
                    logger.warning(f"Erreur dans le fichier de séquence '{filename}': {data}")
        
        return sequences
    
    def reset_variables(self):
        """
        Réinitialise toutes les variables de l'environnement d'exécution
        """
        self._variables = {
            # Variables système prédéfinies
            'HOSTNAME': os.uname().nodename,
            'DATE': datetime.now().strftime('%Y-%m-%d'),
            'TIME': datetime.now().strftime('%H:%M:%S')
        }
    
    def set_variable(self, name: str, value: Any):
        """
        Définit une variable d'environnement
        
        Args:
            name: Nom de la variable
            value: Valeur à assigner
        """
        self._variables[name] = value
    
    def get_variable(self, name: str, default: Any = None) -> Any:
        """
        Récupère une variable d'environnement
        
        Args:
            name: Nom de la variable
            default: Valeur par défaut si la variable n'existe pas
            
        Returns:
            Valeur de la variable ou valeur par défaut
        """
        return self._variables.get(name, default)

    def evaluate_condition(self, condition: str) -> bool:
        """
        Évalue une condition de séquence
        
        Args:
            condition: Expression de condition
            
        Returns:
            Résultat de l'évaluation (True/False)
        """
        if not condition:
            # Une condition vide est toujours vraie
            return True
        
        return self.condition_evaluator.evaluate(condition, self._variables)