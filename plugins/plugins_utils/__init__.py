#!/usr/bin/env python3
"""
Module utilitaire pour les plugins pcUtils.
Contient des fonctions et classes communes utilisées par plusieurs plugins.

Ce module découvre automatiquement tous les fichiers Python dans le répertoire
plugins_utils et expose toutes leurs classes et fonctions pour un import facile.
"""

import os
import sys
import inspect
import importlib
import pkgutil

# Définir __all__ pour contrôler ce qui est importé avec "from plugins_utils import *"
__all__ = []

# Chemin du répertoire courant
package_dir = os.path.dirname(os.path.abspath(__file__))

# Parcourir tous les modules Python dans ce répertoire
for (_, module_name, _) in pkgutil.iter_modules([package_dir]):
    # Ignorer les modules commencant par un underscore
    if module_name.startswith('_'):
        continue

    # Importer le module
    module = importlib.import_module(f".{module_name}", __package__)

    # Trouver toutes les classes et fonctions dans le module
    for name, obj in inspect.getmembers(module):
        # Ignorer les éléments commencant par un underscore (privés)
        if name.startswith('_'):
            continue

        # Ignorer les imports d'autres modules
        if inspect.getmodule(obj) != module:
            continue

        # Ajouter l'élément à ce module
        globals()[name] = obj

        # Ajouter le nom à __all__
        __all__.append(name)
