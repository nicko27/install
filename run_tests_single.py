#!/usr/bin/env python3
import sys
import os
import glob
import unittest
import importlib.util

# Configure le chemin pour inclure les bibliothèques du dossier libs
libs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'libs')

# Ajoute tous les sous-répertoires libs au chemin de recherche
for pkg_dir in glob.glob(os.path.join(libs_dir, '*')):
    # Recherche les répertoires contenant des packages Python
    for subdir in glob.glob(os.path.join(pkg_dir, '*')):
        if os.path.isdir(subdir) and (
            subdir.endswith('.dist-info') or
            os.path.exists(os.path.join(subdir, '__init__.py')) or
            subdir.endswith('.data')
        ):
            # Ajoute le répertoire parent au chemin de recherche
            parent_dir = os.path.dirname(subdir)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
                print(f"Added {parent_dir} to sys.path")

        # Ajoute également le répertoire principal du package au chemin
        if pkg_dir not in sys.path:
            sys.path.insert(0, pkg_dir)
            print(f"Added {pkg_dir} to sys.path")

# Exécute un test spécifique
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python run_tests_single.py <test_file>")
        print("Example: python run_tests_single.py tests/test_template_field.py")
        sys.exit(1)
    
    test_file = sys.argv[1]
    
    # Exécute le test directement en tant que script Python
    print(f"Running test: {test_file}")
    os.system(f"python {test_file}")
