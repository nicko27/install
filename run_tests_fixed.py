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

# Crée un module pytest fictif si nécessaire
if importlib.util.find_spec('pytest') is None:
    print("Creating mock pytest module")
    import types
    sys.modules['pytest'] = types.ModuleType('pytest')
    sys.modules['pytest'].fixture = lambda func=None, **kwargs: func if func else lambda f: f
    sys.modules['pytest'].mark = types.SimpleNamespace()
    sys.modules['pytest'].mark.parametrize = lambda *args, **kwargs: lambda f: f

# Patch pour le module textual.widgets.vertical_scroll
if importlib.util.find_spec('textual.widgets.vertical_scroll') is None:
    print("Creating mock textual.widgets.vertical_scroll module")
    import types
    if 'textual.widgets' not in sys.modules:
        sys.modules['textual.widgets'] = types.ModuleType('textual.widgets')
    sys.modules['textual.widgets.vertical_scroll'] = types.ModuleType('textual.widgets.vertical_scroll')
    # Crée une classe fictive VerticalScroll
    class MockVerticalScroll:
        def __init__(self, *args, **kwargs):
            pass
    sys.modules['textual.widgets.vertical_scroll'].VerticalScroll = MockVerticalScroll

# Patch pour le module ui.report_manager
if importlib.util.find_spec('ui.report_manager') is None:
    print("Creating mock ui.report_manager module")
    import types
    sys.modules['ui.report_manager'] = types.ModuleType('ui.report_manager')
    sys.modules['ui.report_manager.report_manager'] = types.ModuleType('ui.report_manager.report_manager')
    
    # Crée une classe fictive ReportManager
    class MockReportManager:
        def __init__(self, *args, **kwargs):
            pass
    sys.modules['ui.report_manager.report_manager'].ReportManager = MockReportManager

# Exécute un test spécifique si spécifié, sinon exécute tous les tests
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        # Exécute un test spécifique
        test_file = sys.argv[1]
        test_module = test_file.replace('.py', '').replace('/', '.')
        print(f"Running test: {test_module}")
        
        # Importe le module de test
        test_suite = unittest.defaultTestLoader.loadTestsFromName(test_module)
    else:
        # Découvre et exécute tous les tests dans le répertoire tests
        test_suite = unittest.defaultTestLoader.discover('tests')
    
    test_runner = unittest.TextTestRunner(verbosity=2)
    test_runner.run(test_suite)
