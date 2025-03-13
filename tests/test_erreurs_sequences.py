"""
Tests des scénarios d'erreur pour les séquences de plugins.
Vérifie la gestion des erreurs et les cas limites.
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

class TestErreursSequences(unittest.TestCase):
    """Tests des scénarios d'erreur pour les séquences"""

    def setUp(self):
        """Préparation des tests"""
        self.sequences_dir = os.path.join(os.path.dirname(__file__), '..', 'sequences')

    def test_sequence_invalide_yaml(self):
        """Test avec un fichier YAML mal formé"""
        sequence_invalide = """
        name: Test Invalide
        description: YAML mal formé
        plugins:
          - name: add_printer
            variables:
              printer_name: Test
            - mal_indente: true
        """
        
        # Créer un fichier temporaire
        fichier_test = '/tmp/sequence_invalide.yml'
        with open(fichier_test, 'w') as f:
            f.write(sequence_invalide)

        # Tester le chargement
        choice = Choice()
        with self.assertRaises(Exception) as ctx:
            choice.load_sequence(fichier_test)
        
        os.remove(fichier_test)
        self.assertIn('YAML', str(ctx.exception))

    def test_variables_manquantes(self):
        """Test avec des variables requises manquantes"""
        sequence = {
            'name': 'Test Variables Manquantes',
            'plugins': [
                {
                    'name': 'add_printer',
                    'variables': {
                        # printer_name manquant (requis)
                        'printer_ip': '192.168.1.100'
                    }
                }
            ]
        }
        
        fichier_test = '/tmp/variables_manquantes.yml'
        with open(fichier_test, 'w') as f:
            yaml.dump(sequence, f)

        # Charger la séquence et vérifier l'erreur
        choice = Choice()
        choice.load_sequence(fichier_test)
        config = PluginConfig(choice.selected_plugins, sequence_file=fichier_test)
        
        # Vérifier que la validation échoue
        with self.assertRaises(Exception):
            config.validate_config()
        
        os.remove(fichier_test)

    def test_plugin_inexistant(self):
        """Test avec un plugin qui n'existe pas"""
        sequence = {
            'name': 'Test Plugin Inexistant',
            'plugins': [
                {
                    'name': 'plugin_qui_nexiste_pas',
                    'variables': {}
                }
            ]
        }
        
        fichier_test = '/tmp/plugin_inexistant.yml'
        with open(fichier_test, 'w') as f:
            yaml.dump(sequence, f)

        choice = Choice()
        choice.load_sequence(fichier_test)
        
        # Vérifier qu'aucun plugin n'est chargé
        self.assertEqual(len(choice.selected_plugins), 0)
        os.remove(fichier_test)

    def test_valeurs_invalides(self):
        """Test avec des valeurs invalides pour les variables"""
        sequence = {
            'name': 'Test Valeurs Invalides',
            'plugins': [
                {
                    'name': 'add_printer',
                    'variables': {
                        'printer_name': 'Nom Avec Espaces',  # Invalide
                        'printer_ip': 'pas_une_ip',         # Invalide
                        'printer_model': 'ModeleInexistant' # Invalide
                    }
                }
            ]
        }
        
        fichier_test = '/tmp/valeurs_invalides.yml'
        with open(fichier_test, 'w') as f:
            yaml.dump(sequence, f)

        # Charger et vérifier les erreurs de validation
        choice = Choice()
        choice.load_sequence(fichier_test)
        config = PluginConfig(choice.selected_plugins, sequence_file=fichier_test)
        
        # Vérifier les erreurs de validation
        with self.assertRaises(Exception):
            config.validate_config()
        
        os.remove(fichier_test)

    @patch('ui.execution_screen.execution_widget.ExecutionWidget')
    def test_erreur_execution(self, mock_widget):
        """Test de la gestion des erreurs pendant l'exécution"""
        # Simuler une erreur d'exécution
        mock_widget.return_value.start_execution.side_effect = Exception("Erreur test")
        
        sequence = {
            'name': 'Test Erreur Execution',
            'plugins': [
                {
                    'name': 'add_printer',
                    'variables': {
                        'printer_name': 'Test_Printer',
                        'printer_ip': '192.168.1.100',
                        'printer_model': 'KM227'
                    }
                }
            ]
        }
        
        fichier_test = '/tmp/erreur_execution.yml'
        with open(fichier_test, 'w') as f:
            yaml.dump(sequence, f)

        # Tester l'exécution automatique
        choice = Choice()
        choice.load_sequence(fichier_test)
        execution = ExecutionScreen(
            plugins_config={'add_printer_1': sequence['plugins'][0]['variables']},
            auto_execute=True
        )
        
        with self.assertRaises(Exception):
            execution.on_mount()
        
        os.remove(fichier_test)

    def test_sequence_vide(self):
        """Test avec une séquence sans plugins"""
        sequence = {
            'name': 'Séquence Vide',
            'description': 'Test séquence sans plugins',
            'plugins': []
        }
        
        fichier_test = '/tmp/sequence_vide.yml'
        with open(fichier_test, 'w') as f:
            yaml.dump(sequence, f)

        choice = Choice()
        choice.load_sequence(fichier_test)
        
        # Vérifier qu'aucun plugin n'est chargé
        self.assertEqual(len(choice.selected_plugins), 0)
        
        os.remove(fichier_test)

    def test_fichier_non_yaml(self):
        """Test avec un fichier qui n'est pas du YAML"""
        fichier_test = '/tmp/non_yaml.txt'
        with open(fichier_test, 'w') as f:
            f.write("Ceci n'est pas du YAML")

        choice = Choice()
        with self.assertRaises(Exception):
            choice.load_sequence(fichier_test)
        
        os.remove(fichier_test)

if __name__ == '__main__':
    unittest.main()
