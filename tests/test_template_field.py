"""
Tests pour le champ de sélection de template.
"""

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Label, Select
from textual.containers import VerticalGroup
from ui.config_screen.template_field import TemplateField
from ui.config_screen.template_manager import TemplateManager

class TestApp(App):
    """Application de test pour le champ de template"""
    
    def __init__(self, plugin_name: str, field_id: str, fields_by_id: dict):
        super().__init__()
        self.template_field = TemplateField(plugin_name, field_id, fields_by_id)
    
    def compose(self) -> ComposeResult:
        yield self.template_field

@pytest.fixture
def mock_template_manager(monkeypatch):
    """Mock du gestionnaire de templates"""
    class MockTemplateManager:
        def get_plugin_templates(self, plugin_name):
            return {
                'default': {
                    'name': 'Default',
                    'description': 'Template par défaut',
                    'variables': {'var1': 'val1'}
                },
                'custom': {
                    'name': 'Custom',
                    'description': 'Template personnalisé',
                    'variables': {'var2': 'val2'}
                }
            }
        
        def get_template_names(self, plugin_name):
            return ['default', 'custom']
        
        def get_template_description(self, plugin_name, template_name):
            descriptions = {
                'default': 'Template par défaut',
                'custom': 'Template personnalisé'
            }
            return descriptions.get(template_name, '')
        
        def get_default_template(self, plugin_name):
            return {
                'name': 'Default',
                'description': 'Template par défaut',
                'variables': {'var1': 'val1'}
            }
    
    monkeypatch.setattr('ui.config_screen.template_field.TemplateManager', 
                        lambda: MockTemplateManager())

@pytest.fixture
def mock_fields():
    """Mock des champs de configuration"""
    class MockField:
        def __init__(self):
            self.value = None
    
    return {
        'test_plugin_var1': MockField(),
        'test_plugin_var2': MockField()
    }

async def test_template_field_init(mock_template_manager, mock_fields):
    """Vérifie l'initialisation du champ de template"""
    field = TemplateField('test_plugin', 'template', mock_fields)
    assert field.plugin_name == 'test_plugin'
    assert field.field_id == 'template'
    assert field.fields_by_id == mock_fields
    assert len(field.templates) == 2

async def test_template_field_compose(mock_template_manager, mock_fields):
    """Vérifie la composition du champ de template"""
    app = TestApp('test_plugin', 'template', mock_fields)
    async with app.run_test() as pilot:
        # Vérifier la présence du label
        label = app.query_one('Label')
        assert label.text == "Template de configuration:"
        
        # Vérifier le sélecteur
        select = app.query_one('Select')
        assert select.id == "template_test_plugin_template"
        assert len(select.options) == 2
        assert select.value == 'default'  # Template par défaut sélectionné

async def test_template_field_apply_template(mock_template_manager, mock_fields):
    """Vérifie l'application d'un template"""
    field = TemplateField('test_plugin', 'template', mock_fields)
    field._apply_template('default')
    
    # Vérifier que les valeurs ont été appliquées
    assert mock_fields['test_plugin_var1'].value == 'val1'

async def test_template_field_select_changed(mock_template_manager, mock_fields):
    """Vérifie le changement de sélection de template"""
    app = TestApp('test_plugin', 'template', mock_fields)
    async with app.run_test() as pilot:
        select = app.query_one('Select')
        
        # Simuler la sélection d'un template
        await select.press('down')  # Sélectionner 'custom'
        await select.press('enter')
        
        # Vérifier que les valeurs ont été mises à jour
        assert mock_fields['test_plugin_var2'].value == 'val2'

async def test_template_field_no_templates(mock_template_manager, mock_fields, monkeypatch):
    """Vérifie le comportement sans templates"""
    class EmptyTemplateManager:
        def get_plugin_templates(self, plugin_name):
            return {}
    
    monkeypatch.setattr('ui.config_screen.template_field.TemplateManager', 
                        lambda: EmptyTemplateManager())
    
    app = TestApp('test_plugin', 'template', mock_fields)
    async with app.run_test() as pilot:
        # Vérifier qu'aucun élément n'est rendu
        assert len(app.query('Label')) == 0
        assert len(app.query('Select')) == 0
