#!/usr/bin/env python3
"""
Module d'aide à l'import pour les plugins pcUtils.
Ce module permet aux plugins d'importer facilement les modules communs.
"""

import os
import sys

def setup_import_paths():
    """
    Configure les chemins d'import Python pour permettre aux plugins
    de trouver facilement les modules communs.
    
    Cette fonction doit être appelée au début de chaque plugin.
    """
    # Obtenir le répertoire du plugin appelant
    calling_file = sys._getframe(1).f_globals['__file__']
    plugin_dir = os.path.dirname(os.path.abspath(calling_file))
    
    # Obtenir le répertoire parent (plugins/)
    parent_dir = os.path.dirname(plugin_dir)
    
    # Ajouter le répertoire parent au chemin de recherche Python
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)
    
    return True
