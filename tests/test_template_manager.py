"""
Tests pour le gestionnaire de templates.
"""

from ui.config_screen.imports import (
    pytest, Path, tempfile, shutil, os, yaml
)

from ui.config_screen.template_manager import TemplateManager

@pytest.fixture
def temp_templates_dir():
    """Crée un dossier temporaire pour les tests"""
    with tempfile.TemporaryDirectory() as temp_dir:
        templates_dir = Path(temp_dir) / 'templates'
        templates_dir.mkdir()
        yield templates_dir

@pytest.fixture
def template_manager(temp_templates_dir, monkeypatch):
    """Crée une instance de TemplateManager avec un dossier temporaire"""
    manager = TemplateManager()
    monkeypatch.setattr(manager, 'templates_dir', temp_templates_dir)
    return manager

def create_test_template(templates_dir: Path, plugin_name: str, template_name: str, content: dict):
    """Crée un fichier de template de test"""
    plugin_dir = templates_dir / plugin_name
    plugin_dir.mkdir(exist_ok=True)
    template_file = plugin_dir / f"{template_name}.yml"
    with open(template_file, 'w') as f:
        yaml.dump(content, f)

def test_get_templates_dir(template_manager, temp_templates_dir):
    """Vérifie que le dossier de templates est correctement récupéré"""
    assert template_manager._get_templates_dir() == temp_templates_dir

def test_load_schema_empty(template_manager):
    """Vérifie que le schéma par défaut est vide si le fichier n'existe pas"""
    schema = template_manager._load_schema()
    assert schema == {}

def test_validate_template_valid(template_manager):
    """Vérifie la validation d'un template valide"""
    template = {
        'name': 'Test Template',
        'description': 'Template de test',
        'variables': {
            'test_var': 'test_value'
        }
    }
    assert template_manager._validate_template(template) is True

def test_validate_template_invalid(template_manager):
    """Vérifie le rejet d'un template invalide"""
    invalid_templates = [
        {},  # Vide
        {'name': 'Test'},  # Manque description et variables
        {'name': 'Test', 'description': 'Test', 'variables': 'not_a_dict'}  # Variables non dictionnaire
    ]
    for template in invalid_templates:
        assert template_manager._validate_template(template) is False

def test_get_plugin_templates(template_manager, temp_templates_dir):
    """Vérifie la récupération des templates d'un plugin"""
    test_templates = {
        'default': {
            'name': 'Default Template',
            'description': 'Template par défaut',
            'variables': {'var1': 'val1'}
        },
        'custom': {
            'name': 'Custom Template',
            'description': 'Template personnalisé',
            'variables': {'var2': 'val2'}
        }
    }
    
    for name, content in test_templates.items():
        create_test_template(temp_templates_dir, 'test_plugin', name, content)
    
    templates = template_manager.get_plugin_templates('test_plugin')
    assert len(templates) == 2
    assert 'default' in templates
    assert 'custom' in templates
    assert templates['default']['variables']['var1'] == 'val1'

def test_get_default_template(template_manager, temp_templates_dir):
    """Vérifie la récupération du template par défaut"""
    default_content = {
        'name': 'Default',
        'description': 'Template par défaut',
        'variables': {'default_var': 'default_val'}
    }
    create_test_template(temp_templates_dir, 'test_plugin', 'default', default_content)
    
    default = template_manager.get_default_template('test_plugin')
    assert default is not None
    assert default['name'] == 'Default'
    assert default['variables']['default_var'] == 'default_val'

def test_get_template_names(template_manager, temp_templates_dir):
    """Vérifie la liste des noms de templates"""
    templates = {
        'default': {'name': 'Default', 'description': 'Default', 'variables': {}},
        'custom1': {'name': 'Custom 1', 'description': 'Custom 1', 'variables': {}},
        'custom2': {'name': 'Custom 2', 'description': 'Custom 2', 'variables': {}}
    }
    
    for name, content in templates.items():
        create_test_template(temp_templates_dir, 'test_plugin', name, content)
    
    names = template_manager.get_template_names('test_plugin')
    assert set(names) == {'default', 'custom1', 'custom2'}

def test_get_template_description(template_manager, temp_templates_dir):
    """Vérifie la récupération de la description d'un template"""
    content = {
        'name': 'Test',
        'description': 'Description de test',
        'variables': {}
    }
    create_test_template(temp_templates_dir, 'test_plugin', 'test', content)
    
    description = template_manager.get_template_description('test_plugin', 'test')
    assert description == 'Description de test'

def test_get_template_variables(template_manager, temp_templates_dir):
    """Vérifie la récupération des variables d'un template"""
    content = {
        'name': 'Test',
        'description': 'Test',
        'variables': {
            'var1': 'val1',
            'var2': 'val2'
        }
    }
    create_test_template(temp_templates_dir, 'test_plugin', 'test', content)
    
    variables = template_manager.get_template_variables('test_plugin', 'test')
    assert variables == {'var1': 'val1', 'var2': 'val2'}
