import logging
import os
import sys

def setup_logging():
    """Configure le système de logging"""
    log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, 'debug.log')
    
    # Configuration du logger racine
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            # Fichier de log
            logging.FileHandler(log_file, mode='w', encoding='utf-8')
        ]
    )
    
    # Configurer un logger spécifique pour l'interface utilisateur
    logger = logging.getLogger('install_ui')
    logger.setLevel(logging.DEBUG)
    
    return logger
