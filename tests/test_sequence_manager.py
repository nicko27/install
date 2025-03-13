"""
Tests pour le gestionnaire de séquences.
"""

from ui.config_screen.imports import (
    pytest, Path, tempfile, shutil, os, yaml,
    MagicMock, patch
)
from ui.sequence_manager.sequence_manager import SequenceManager

@pytest.fixture
def temp_sequences_dir():
    """Crée un dossier temporaire pour les tests"""
    with tempfile.TemporaryDirectory() as temp_dir:
        sequences_dir = Path(temp_dir) / 'sequences'
        sequences_dir.mkdir()
        yield sequences_dir

@pytest.fixture
def sequence_manager(temp_sequences_dir, monkeypatch):
    """Crée une instance de SequenceManager avec un dossier temporaire"""
    manager = SequenceManager()
    monkeypatch.setattr(manager, 'sequences_dir', temp_sequences_dir)
    return manager

def create_test_sequence(sequences_dir: Path, sequence_name: str, content: dict):
    """Crée un fichier de séquence de test"""
    sequence_file = sequences_dir / f"{sequence_name}.yml"
    with open(sequence_file, 'w') as f:
        yaml.dump(content, f)

def test_load_sequence_valid(sequence_manager, temp_sequences_dir):
    """Vérifie le chargement d'une séquence valide"""
    sequence = {
        'name': 'Test Sequence',
        'description': 'Séquence de test',
        'steps': [
            {
                'plugin': 'test_plugin',
                'config': {'param': 'value'}
            }
        ]
    }
    create_test_sequence(temp_sequences_dir, 'test_sequence', sequence)
    
    loaded = sequence_manager.load_sequence('test_sequence')
    assert loaded is not None
    assert loaded['name'] == 'Test Sequence'
    assert len(loaded['steps']) == 1

def test_load_sequence_invalid(sequence_manager, temp_sequences_dir):
    """Vérifie le rejet d'une séquence invalide"""
    invalid_sequence = {
        'name': 'Invalid',
        'description': 'Missing steps'
    }
    create_test_sequence(temp_sequences_dir, 'invalid', invalid_sequence)
    
    loaded = sequence_manager.load_sequence('invalid')
    assert loaded is None

def test_validate_step_conditions(sequence_manager):
    """Vérifie la validation des conditions d'une étape"""
    step = {
        'plugin': 'test_plugin',
        'conditions': [
            {
                'variable': 'TEST_STATUS',
                'operator': '==',
                'value': True
            }
        ]
    }
    assert sequence_manager._validate_step(step) is True

def test_validate_step_invalid_conditions(sequence_manager):
    """Vérifie le rejet de conditions invalides"""
    step = {
        'plugin': 'test_plugin',
        'conditions': [
            {
                'variable': 'TEST_STATUS',
                'operator': 'invalid',  # Opérateur invalide
                'value': True
            }
        ]
    }
    assert sequence_manager._validate_step(step) is False

def test_evaluate_conditions_true(sequence_manager):
    """Vérifie l'évaluation positive des conditions"""
    sequence_manager.environment = {
        'TEST_STATUS': True,
        'COUNT': 5
    }
    
    conditions = [
        {'variable': 'TEST_STATUS', 'operator': '==', 'value': True},
        {'variable': 'COUNT', 'operator': '>', 'value': 3}
    ]
    
    assert sequence_manager.evaluate_conditions(conditions) is True

def test_evaluate_conditions_false(sequence_manager):
    """Vérifie l'évaluation négative des conditions"""
    sequence_manager.environment = {
        'TEST_STATUS': False,
        'COUNT': 2
    }
    
    conditions = [
        {'variable': 'TEST_STATUS', 'operator': '==', 'value': True},
        {'variable': 'COUNT', 'operator': '>', 'value': 3}
    ]
    
    assert sequence_manager.evaluate_conditions(conditions) is False

def test_update_environment_default_name(sequence_manager):
    """Vérifie la mise à jour de l'environnement avec nom par défaut"""
    sequence_manager.update_environment('test_plugin', True)
    assert sequence_manager.environment['TEST_PLUGIN_STATUS'] is True

def test_update_environment_custom_name(sequence_manager):
    """Vérifie la mise à jour de l'environnement avec nom personnalisé"""
    sequence_manager.update_environment('test_plugin', True, 'CUSTOM_VAR')
    assert sequence_manager.environment['CUSTOM_VAR'] is True

def test_should_continue_conditions_not_met(sequence_manager):
    """Vérifie la continuation si les conditions ne sont pas satisfaites"""
    sequence_manager.environment = {'TEST_STATUS': False}
    step = {
        'plugin': 'test_plugin',
        'conditions': [
            {'variable': 'TEST_STATUS', 'operator': '==', 'value': True}
        ]
    }
    
    assert sequence_manager.should_continue(step, True) is True

def test_should_continue_stop_on_fail(sequence_manager):
    """Vérifie l'arrêt sur échec si configuré"""
    sequence_manager.environment = {'TEST_PLUGIN_STATUS': False}
    step = {'plugin': 'test_plugin'}
    
    assert sequence_manager.should_continue(step, True) is False

def test_should_continue_no_result(sequence_manager):
    """Vérifie la continuation si pas de résultat"""
    step = {'plugin': 'test_plugin'}
    assert sequence_manager.should_continue(step, True) is True

def test_evaluate_condition_in_operator(sequence_manager):
    """Vérifie l'opérateur 'in'"""
    assert sequence_manager._evaluate_condition(5, 'in', [1, 5, 10]) is True
    assert sequence_manager._evaluate_condition(3, 'in', [1, 5, 10]) is False

def test_evaluate_condition_not_in_operator(sequence_manager):
    """Vérifie l'opérateur 'not in'"""
    assert sequence_manager._evaluate_condition(3, 'not in', [1, 5, 10]) is True
    assert sequence_manager._evaluate_condition(5, 'not in', [1, 5, 10]) is False
