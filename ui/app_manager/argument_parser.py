"""
Module de gestion des arguments de ligne de commande.
"""

import argparse
from ..utils.logging import get_logger

logger = get_logger('argument_parser')

class ArgumentParser:
    """Gestion des arguments de ligne de commande"""
    
    @staticmethod
    def parse_args():
        """Parse les arguments de ligne de commande"""
        parser = argparse.ArgumentParser(description='pcUtils')
        
        # Mode automatique
        parser.add_argument('--auto', '-a', 
                          help='Mode auto utilisant une séquence',
                          action='store_true')
        parser.add_argument('--sequence', '-s',
                          help='Chemin vers le fichier de séquence')
        parser.add_argument('--shortcut',
                          help='Shortcut de la séquence à utiliser')
        
        # Mode plugin unique
        parser.add_argument('--plugin',
                          help='Nom du plugin à exécuter')
        parser.add_argument('--config',
                          help='Fichier de configuration')
        parser.add_argument('--params',
                          help='Paramètres supplémentaires (format: key=value)',
                          nargs='*')
        

        
        return parser.parse_args()
