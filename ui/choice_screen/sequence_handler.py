"""
Gestionnaire de séquences pour l'écran de sélection.
Gère le chargement et la validation des séquences.
"""

from pathlib import Path
from typing import List, Dict, Optional, Any
from ruamel.yaml import YAML
from logging import getLogger

logger = getLogger('sequence_handler')
yaml = YAML()

class SequenceHandler:
    """Gestionnaire de séquences pour l'écran de sélection"""

    def __init__(self):
        """Initialise le gestionnaire de séquences"""
        self.sequences_dir = Path('sequences')
        logger.debug(f"Dossier des séquences : {self.sequences_dir}")

    def load_sequence(self, sequence_path: str) -> Optional[Dict[str, Any]]:
        """
        Charge une séquence depuis un fichier YAML.
        
        Args:
            sequence_path: Chemin vers le fichier de séquence
            
        Returns:
            Données de la séquence ou None en cas d'erreur
        """
        try:
            sequence_file = Path(sequence_path)
            if not sequence_file.exists():
                logger.error(f"Fichier de séquence non trouvé : {sequence_path}")
                return None

            with open(sequence_file, 'r', encoding='utf-8') as f:
                sequence = yaml.load(f)

            if not self._validate_sequence(sequence):
                logger.error(f"Format de séquence invalide : {sequence_path}")
                return None

            logger.info(f"Séquence chargée : {sequence.get('name', 'Sans nom')}")
            return sequence

        except Exception as e:
            logger.error(f"Erreur lors du chargement de la séquence : {e}")
            return None

    def _validate_sequence(self, sequence: dict) -> bool:
        """
        Valide le format d'une séquence.
        
        Args:
            sequence: Données de la séquence à valider
            
        Returns:
            True si la séquence est valide
        """
        if not isinstance(sequence, dict):
            logger.warning("La séquence doit être un dictionnaire")
            return False

        required_fields = ['name', 'description', 'plugins']
        for field in required_fields:
            if field not in sequence:
                logger.warning(f"Champ requis manquant : {field}")
                return False

        if not isinstance(sequence['plugins'], list):
            logger.warning("Le champ 'plugins' doit être une liste")
            return False

        for plugin in sequence['plugins']:
            if not self._validate_plugin_config(plugin):
                return False

        return True

    def _validate_plugin_config(self, config: dict) -> bool:
        """
        Valide la configuration d'un plugin dans une séquence.
        
        Args:
            config: Configuration du plugin à valider
            
        Returns:
            True si la configuration est valide
        """
        if not isinstance(config, dict):
            logger.warning("La configuration du plugin doit être un dictionnaire")
            return False

        if 'name' not in config:
            logger.warning("Le nom du plugin est requis")
            return False

        # Vérifier les conditions si présentes
        if 'conditions' in config:
            if not isinstance(config['conditions'], list):
                logger.warning("Les conditions doivent être une liste")
                return False

            for condition in config['conditions']:
                if not self._validate_condition(condition):
                    return False

        return True

    def _validate_condition(self, condition: dict) -> bool:
        """
        Valide une condition dans la configuration d'un plugin.
        
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

    def get_available_sequences(self) -> List[Dict[str, Any]]:
        """
        Récupère la liste des séquences disponibles.
        
        Returns:
            Liste des séquences avec leurs métadonnées
        """
        sequences = []
        
        if not self.sequences_dir.exists():
            logger.warning(f"Dossier des séquences non trouvé : {self.sequences_dir}")
            return sequences

        for seq_file in self.sequences_dir.glob('*.yml'):
            try:
                with open(seq_file, 'r', encoding='utf-8') as f:
                    sequence = yaml.load(f)
                    if self._validate_sequence(sequence):
                        sequences.append({
                            'name': sequence.get('name', seq_file.stem),
                            'description': sequence.get('description', ''),
                            'file_name': seq_file.name,
                            'plugins_count': len(sequence.get('plugins', []))
                        })
                    else:
                        logger.warning(f"Séquence invalide ignorée : {seq_file.name}")
            except Exception as e:
                logger.error(f"Erreur lors du chargement de {seq_file.name} : {e}")

        return sorted(sequences, key=lambda x: x['name'].lower())
