#!/usr/bin/env python3
import sys
import os
import glob
import importlib.util
import types

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

# Crée un module pytest fictif
print("Creating mock pytest module")
sys.modules['pytest'] = types.ModuleType('pytest')
sys.modules['pytest'].fixture = lambda func=None, **kwargs: func if func else lambda f: f
sys.modules['pytest'].mark = types.SimpleNamespace()
sys.modules['pytest'].mark.parametrize = lambda *args, **kwargs: lambda f: f

# Crée des mocks pour textual
print("Creating mock textual modules")
# Pour textual.containers
sys.modules['textual.containers'] = types.ModuleType('textual.containers')
class MockVerticalGroup:
    def __init__(self, *args, **kwargs):
        pass
sys.modules['textual.containers'].VerticalGroup = MockVerticalGroup
sys.modules['textual.containers'].HorizontalGroup = type('HorizontalGroup', (), {})
sys.modules['textual.containers'].Horizontal = type('Horizontal', (), {})
sys.modules['textual.containers'].Vertical = type('Vertical', (), {})

# Pour textual.app
sys.modules['textual.app'] = types.ModuleType('textual.app')
sys.modules['textual.app'].App = type('App', (), {'__init__': lambda self, *args, **kwargs: None})
sys.modules['textual.app'].ComposeResult = type('ComposeResult', (), {})

# Pour textual.widgets
sys.modules['textual.widgets'] = types.ModuleType('textual.widgets')
sys.modules['textual.widgets'].Label = type('Label', (), {'__init__': lambda self, *args, **kwargs: None})
sys.modules['textual.widgets'].Select = type('Select', (), {'__init__': lambda self, *args, **kwargs: None})

# Pour textual.widgets.vertical_scroll
sys.modules['textual.widgets.vertical_scroll'] = types.ModuleType('textual.widgets.vertical_scroll')
sys.modules['textual.widgets.vertical_scroll'].VerticalScroll = type('VerticalScroll', (), {})

# Pour ui.report_manager
sys.modules['ui.report_manager'] = types.ModuleType('ui.report_manager')
sys.modules['ui.report_manager.report_manager'] = types.ModuleType('ui.report_manager.report_manager')
sys.modules['ui.report_manager.report_manager'].ReportManager = type('ReportManager', (), {'__init__': lambda self, *args, **kwargs: None})

# Exécute le test spécifié
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_test_with_mocks.py <test_file>")
        sys.exit(1)
    
    test_file = sys.argv[1]
    print(f"Running test: {test_file}")
    
    # Exécute le test comme un script Python
    with open(test_file, 'r') as f:
        code = compile(f.read(), test_file, 'exec')
        exec(code, {'__name__': '__main__', '__file__': test_file})
