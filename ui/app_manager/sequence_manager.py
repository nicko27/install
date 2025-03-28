"""
Module de gestion des séquences.
"""

import os
from ruamel.yaml import YAML
from ..utils.logging import get_logger

logger = get_logger('sequence_manager')
yaml = YAML()

class SequenceManager:
    """Gestion des séquences"""
    
    @staticmethod
    def find_sequence_by_shortcut(shortcut):
        """
        Trouve une séquence par son shortcut.
        
        Args:
            shortcut (str): Le shortcut à rechercher
            
        Returns:
            tuple: (chemin_sequence, données_sequence) ou (None, None) si non trouvé
        """
        sequences_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'sequences')
        matching_sequences = []
        
        # Parcourir tous les fichiers .yml dans le dossier sequences
        for file in os.listdir(sequences_dir):
            if file.endswith('.yml'):
                try:
                    with open(os.path.join(sequences_dir, file), 'r') as f:
                        sequence = yaml.load(f)
                        if 'shortcut' in sequence:
                            shortcuts = sequence['shortcut']
                            if isinstance(shortcuts, str) and shortcuts == shortcut:
                                matching_sequences.append((file, sequence))
                            elif isinstance(shortcuts, list) and shortcut in shortcuts:
                                matching_sequences.append((file, sequence))
                except Exception as e:
                    logger.error(f"Erreur lors de la lecture du fichier de séquence {file}: {e}")
                    continue
        
        if len(matching_sequences) == 0:
            logger.error(f"Aucune séquence trouvée avec le shortcut '{shortcut}'")
            return None, None
        elif len(matching_sequences) > 1:
            logger.error(f"Plusieurs séquences trouvées avec le shortcut '{shortcut}':")
            for file, _ in matching_sequences:
                logger.error(f"- {file}")
            return None, None
        else:
            return os.path.join(sequences_dir, matching_sequences[0][0]), matching_sequences[0][1]
            
    @staticmethod
    def load_sequence(sequence_path):
        """
        Charge une séquence depuis un fichier.
        
        Args:
            sequence_path (str): Chemin vers le fichier de séquence
            
        Returns:
            dict: Données de la séquence ou None si erreur
        """
        try:
            with open(sequence_path, 'r') as f:
                return yaml.load(f)
        except Exception as e:
            logger.error(f"Erreur lors du chargement de la séquence: {e}")
            return None
