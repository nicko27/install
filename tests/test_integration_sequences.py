"""
Tests d'intégration pour les séquences de plugins.
Vérifie le fonctionnement complet avec les vrais fichiers de séquence.
"""

import os
import sys
import unittest
from ruamel.yaml import YAML

# Ajouter le répertoire parent au PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ui.choice_screen.choice_screen import Choice
from ui.config_screen.config_screen import PluginConfig
from ui.execution_screen.execution_screen import ExecutionScreen

yaml = YAML()

class TestIntegrationSequences(unittest.TestCase):
    """Tests d'intégration des séquences avec les vrais plugins"""

    def setUp(self):
        """Initialisation avant chaque test"""
        self.sequences_dir = os.path.join(os.path.dirname(__file__), '..', 'sequences')
        self.installation_sequence = os.path.join(self.sequences_dir, 'installation_imprimante.yml')
        self.suppression_sequence = os.path.join(self.sequences_dir, 'suppression_imprimante.yml')

    def test_installation_sequence(self):
        """Test de la séquence d'installation complète"""
        # Vérifier que le fichier existe
        self.assertTrue(os.path.exists(self.installation_sequence),
                       "Le fichier de séquence d'installation n'existe pas")

        # Charger et vérifier la séquence
        with open(self.installation_sequence, 'r') as f:
            sequence = yaml.load(f)

        # Vérifier la structure
        self.assertIn('name', sequence)
        self.assertIn('description', sequence)
        self.assertIn('plugins', sequence)
        self.assertEqual(len(sequence['plugins']), 2)

        # Vérifier les plugins
        plugins = sequence['plugins']
        self.assertEqual(plugins[0]['name'], 'add_printer')
        self.assertEqual(plugins[1]['name'], 'scan_plugin')

        # Vérifier les variables requises
        printer_vars = plugins[0]['variables']
        self.assertIn('printer_name', printer_vars)
        self.assertIn('printer_ip', printer_vars)
        self.assertIn('printer_model', printer_vars)

        scan_vars = plugins[1]['variables']
        self.assertIn('user', scan_vars)
        self.assertIn('password', scan_vars)
        self.assertIn('scan_directory', scan_vars)

    def test_suppression_sequence(self):
        """Test de la séquence de suppression"""
        # Vérifier que le fichier existe
        self.assertTrue(os.path.exists(self.suppression_sequence),
                       "Le fichier de séquence de suppression n'existe pas")

        # Charger et vérifier la séquence
        with open(self.suppression_sequence, 'r') as f:
            sequence = yaml.load(f)

        # Vérifier la structure
        self.assertIn('name', sequence)
        self.assertIn('description', sequence)
        self.assertIn('plugins', sequence)
        self.assertEqual(len(sequence['plugins']), 2)

        # Vérifier les plugins
        plugins = sequence['plugins']
        self.assertEqual(plugins[0]['name'], 'delete_printer')
        self.assertEqual(plugins[1]['name'], 'scan_plugin')

        # Vérifier les variables requises
        delete_vars = plugins[0]['variables']
        self.assertIn('printer_name', delete_vars)
        self.assertIn('remove_drivers', delete_vars)
        self.assertTrue(delete_vars['remove_drivers'])

    def test_sequence_in_choice_screen(self):
        """Test de l'affichage des séquences dans l'écran de sélection"""
        choice = Choice()
        cards = choice.create_plugin_cards()

        # Vérifier que les séquences sont présentes
        sequence_cards = [card for card in cards 
                         if hasattr(card, 'plugin_name') and 
                         card.plugin_name.startswith('__sequence__')]
        
        self.assertGreater(len(sequence_cards), 0,
                          "Aucune séquence n'apparaît dans l'écran de sélection")

    def test_sequence_variables_override(self):
        """Test de la modification des variables préremplies"""
        # Charger la séquence
        choice = Choice()
        choice.load_sequence(self.installation_sequence)

        # Créer l'écran de configuration
        config = PluginConfig(choice.selected_plugins, sequence_file=self.installation_sequence)

        # Vérifier que les variables sont modifiables
        printer_key = f"add_printer_{choice.instance_counter['add_printer']}"
        original_name = config.current_config[printer_key]['printer_name']

        # Modifier une variable
        new_name = "Nouveau_Nom"
        config.current_config[printer_key]['printer_name'] = new_name

        # Vérifier que la modification est possible
        self.assertEqual(config.current_config[printer_key]['printer_name'], new_name)
        self.assertNotEqual(config.current_config[printer_key]['printer_name'], original_name)

    def test_sequence_execution_order(self):
        """Test de l'ordre d'exécution des plugins dans une séquence"""
        choice = Choice()
        choice.load_sequence(self.installation_sequence)

        # Vérifier l'ordre des plugins
        plugin_order = [name for name, _ in choice.selected_plugins]
        expected_order = ['add_printer', 'scan_plugin']
        
        self.assertEqual(plugin_order, expected_order,
                        "L'ordre des plugins ne correspond pas à la séquence")

if __name__ == '__main__':
    unittest.main()
