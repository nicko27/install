"""
Tests pour la fonctionnalité des séquences de plugins.
"""

import os
import sys
import unittest
from ruamel.yaml import YAML
from unittest.mock import patch, MagicMock

# Ajouter le répertoire parent au PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ui.choice_screen.choice_screen import Choice
from ui.config_screen.config_screen import PluginConfig
from ui.execution_screen.execution_screen import ExecutionScreen

yaml = YAML()

class TestSequences(unittest.TestCase):
    """Tests des séquences de plugins"""

    def setUp(self):
        """Initialisation des tests"""
        self.test_sequence = {
            'name': 'Test Sequence',
            'description': 'Séquence de test',
            'plugins': [
                {
                    'name': 'add_printer',
                    'variables': {
                        'printer_name': 'Test_Printer',
                        'printer_ip': '192.168.1.100',
                        'printer_model': 'KM227'
                    }
                },
                {
                    'name': 'scan_plugin',
                    'variables': {
                        'user': 'scan',
                        'password': 'test123',
                        'confirm': True,
                        'scan_directory': '/test/scan'
                    }
                }
            ]
        }
        
        # Créer un fichier de séquence temporaire pour les tests
        self.test_sequence_file = '/tmp/test_sequence.yml'
        with open(self.test_sequence_file, 'w') as f:
            yaml.dump(self.test_sequence, f)

    def tearDown(self):
        """Nettoyage après les tests"""
        if os.path.exists(self.test_sequence_file):
            os.remove(self.test_sequence_file)

    def test_sequence_loading(self):
        """Test du chargement d'une séquence"""
        choice_screen = Choice()
        choice_screen.load_sequence(self.test_sequence_file)
        
        # Vérifier que les plugins sont chargés dans l'ordre
        self.assertEqual(len(choice_screen.selected_plugins), 2)
        self.assertEqual(choice_screen.selected_plugins[0][0], 'add_printer')
        self.assertEqual(choice_screen.selected_plugins[1][0], 'scan_plugin')

    def test_sequence_config_prefill(self):
        """Test du préremplissage des configurations"""
        config_screen = PluginConfig(
            plugin_instances=[('add_printer', 1), ('scan_plugin', 1)],
            sequence_file=self.test_sequence_file
        )
        
        # Vérifier que les variables sont préremplies
        self.assertIn('add_printer_1', config_screen.current_config)
        self.assertIn('scan_plugin_1', config_screen.current_config)
        
        # Vérifier les valeurs
        printer_config = config_screen.current_config['add_printer_1']
        self.assertEqual(printer_config['printer_name'], 'Test_Printer')
        self.assertEqual(printer_config['printer_ip'], '192.168.1.100')
        
        scan_config = config_screen.current_config['scan_plugin_1']
        self.assertEqual(scan_config['user'], 'scan')
        self.assertEqual(scan_config['scan_directory'], '/test/scan')

    @patch('ui.execution_screen.execution_widget.ExecutionWidget.start_execution')
    def test_auto_execution(self, mock_start):
        """Test de l'exécution automatique"""
        execution_screen = ExecutionScreen(
            plugins_config={
                'add_printer_1': self.test_sequence['plugins'][0]['variables'],
                'scan_plugin_1': self.test_sequence['plugins'][1]['variables']
            },
            auto_execute=True
        )
        
        # Vérifier que l'exécution automatique est déclenchée
        self.assertTrue(execution_screen.auto_execute)
        execution_screen.on_mount()
        mock_start.assert_called_once()

    def test_sequence_validation(self):
        """Test de la validation des séquences"""
        # Séquence invalide sans plugins
        invalid_sequence = {
            'name': 'Invalid',
            'description': 'Test invalide'
        }
        
        with self.assertRaises(KeyError):
            choice_screen = Choice()
            with open('/tmp/invalid.yml', 'w') as f:
                yaml.dump(invalid_sequence, f)
            choice_screen.load_sequence('/tmp/invalid.yml')
            os.remove('/tmp/invalid.yml')

        # Séquence invalide avec plugin inexistant
        invalid_plugin_sequence = {
            'name': 'Invalid Plugin',
            'plugins': [
                {
                    'name': 'nonexistent_plugin',
                    'variables': {}
                }
            ]
        }
        
        with self.assertRaises(Exception):
            choice_screen = Choice()
            with open('/tmp/invalid_plugin.yml', 'w') as f:
                yaml.dump(invalid_plugin_sequence, f)
            choice_screen.load_sequence('/tmp/invalid_plugin.yml')
            os.remove('/tmp/invalid_plugin.yml')

if __name__ == '__main__':
    unittest.main()
