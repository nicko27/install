"""
Tests pour l'exécution conditionnelle des séquences.
"""

from ui.config_screen.imports import (
    pytest, Path, tempfile, shutil, os, yaml,
    MagicMock, patch
)
from ui.sequence_manager.sequence_manager import SequenceManager

@pytest.fixture
def sequence_manager():
    """Crée une instance de SequenceManager pour les tests"""
    return SequenceManager()

@pytest.fixture
def mock_environment():
    """Crée un environnement de test avec des variables"""
    return {
        'NETWORK_STATUS': True,
        'SYSTEM_STATUS': True,
        'PRINTER_INFO': {
            'name': 'TestPrinter',
            'ip': '192.168.1.100'
        },
        'DRIVER_INSTALL_STATUS': True,
        'ADD_PRINTER_STATUS': True
    }

def test_execution_conditionnelle_success(sequence_manager, mock_environment):
    """Vérifie l'exécution conditionnelle réussie"""
    sequence_manager.environment = mock_environment.copy()
    
    step = {
        'plugin': 'print_test',
        'conditions': [
            {
                'variable': 'ADD_PRINTER_STATUS',
                'operator': '==',
                'value': True
            },
            {
                'variable': 'DRIVER_INSTALL_STATUS',
                'operator': '==',
                'value': True
            }
        ]
    }
    
    assert sequence_manager.should_continue(step, False) is True

def test_execution_conditionnelle_failure(sequence_manager, mock_environment):
    """Vérifie l'échec de l'exécution conditionnelle"""
    env = mock_environment.copy()
    env['ADD_PRINTER_STATUS'] = False
    sequence_manager.environment = env
    
    step = {
        'plugin': 'print_test',
        'conditions': [
            {
                'variable': 'ADD_PRINTER_STATUS',
                'operator': '==',
                'value': True
            }
        ]
    }
    
    assert sequence_manager.should_continue(step, False) is True  # Continue car conditions non satisfaites

def test_stop_on_first_fail(sequence_manager):
    """Vérifie l'arrêt sur première erreur"""
    sequence_manager.environment = {'TEST_PLUGIN_STATUS': False}
    step = {'plugin': 'test_plugin'}
    
    assert sequence_manager.should_continue(step, True) is False

def test_continue_on_fail(sequence_manager):
    """Vérifie la continuation malgré l'erreur"""
    sequence_manager.environment = {'TEST_PLUGIN_STATUS': False}
    step = {'plugin': 'test_plugin'}
    
    assert sequence_manager.should_continue(step, False) is True

def test_variable_export_default(sequence_manager):
    """Vérifie l'export de variable avec nom par défaut"""
    sequence_manager.update_environment('test_plugin', True)
    assert sequence_manager.environment['TEST_PLUGIN_STATUS'] is True

def test_variable_export_custom(sequence_manager):
    """Vérifie l'export de variable avec nom personnalisé"""
    sequence_manager.update_environment('test_plugin', True, 'CUSTOM_VAR')
    assert sequence_manager.environment['CUSTOM_VAR'] is True

def test_conditions_complexes(sequence_manager):
    """Vérifie l'évaluation de conditions complexes"""
    sequence_manager.environment = {
        'COUNT': 5,
        'STATUS': 'ready',
        'VALUES': [1, 2, 3],
        'ERRORS': []
    }
    
    conditions = [
        {'variable': 'COUNT', 'operator': '>=', 'value': 3},
        {'variable': 'STATUS', 'operator': '==', 'value': 'ready'},
        {'variable': 'VALUES', 'operator': 'in', 'value': 2},
        {'variable': 'ERRORS', 'operator': '==', 'value': []}
    ]
    
    assert sequence_manager.evaluate_conditions(conditions) is True

def test_conditions_avec_types_differents(sequence_manager):
    """Vérifie la gestion des types différents dans les conditions"""
    sequence_manager.environment = {
        'NUMBER': 42,
        'TEXT': 'test',
        'MIXED': [1, 'two', 3.0]
    }
    
    # Test avec nombre
    assert sequence_manager._evaluate_condition(42, '==', '42') is False
    
    # Test avec liste
    assert sequence_manager._evaluate_condition(
        [1, 'two', 3.0], '==', [1, 'two', 3.0]
    ) is True

def test_operateurs_avances(sequence_manager):
    """Vérifie les opérateurs avancés"""
    # Test in
    assert sequence_manager._evaluate_condition(5, 'in', [1, 5, 10]) is True
    assert sequence_manager._evaluate_condition('test', 'in', 'testing') is True
    
    # Test not in
    assert sequence_manager._evaluate_condition(7, 'not in', [1, 5, 10]) is True
    assert sequence_manager._evaluate_condition('x', 'not in', 'test') is True

def test_gestion_erreurs_evaluation(sequence_manager):
    """Vérifie la gestion des erreurs lors de l'évaluation"""
    # Test avec types incompatibles
    assert sequence_manager._evaluate_condition(
        'test', '>', 42
    ) is False
    
    # Test avec opérateur invalide
    assert sequence_manager._evaluate_condition(
        42, 'invalid', 42
    ) is False

def test_sequence_complete(sequence_manager, mock_environment):
    """Vérifie l'exécution d'une séquence complète"""
    sequence_manager.environment = mock_environment.copy()
    
    steps = [
        {
            'plugin': 'network_check',
            'export_result': 'NETWORK_STATUS'
        },
        {
            'plugin': 'add_printer',
            'conditions': [
                {'variable': 'NETWORK_STATUS', 'operator': '==', 'value': True}
            ]
        },
        {
            'plugin': 'print_test',
            'conditions': [
                {'variable': 'ADD_PRINTER_STATUS', 'operator': '==', 'value': True}
            ]
        }
    ]
    
    # Vérifier chaque étape
    for step in steps:
        assert sequence_manager.should_continue(step, False) is True
        if 'export_result' in step:
            sequence_manager.update_environment(
                step['plugin'],
                True,
                step['export_result']
            )
        else:
            sequence_manager.update_environment(step['plugin'], True)
