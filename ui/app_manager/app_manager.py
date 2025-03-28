"""
Module principal de gestion de l'application.
"""

import sys
from textual.app import App
from ..utils.logging import get_logger
from ..choice_screen.choice_screen import Choice
from ..config_screen.config_screen import PluginConfig
from ..execution_screen.execution_screen import ExecutionScreen
from ..config_screen.auto_config import AutoConfig
from .argument_parser import ArgumentParser
from .config_loader import ConfigLoader
from .sequence_manager import SequenceManager

logger = get_logger('app_manager')

class AppManager:
    """Gestionnaire principal de l'application"""
    
    def __init__(self):
        """Initialisation du gestionnaire"""
        self.args = ArgumentParser.parse_args()
        
    def run(self):
        """Lance l'application dans le mode approprié"""
        if self.args.auto:
            self._run_auto_mode()
        elif self.args.plugin:
            self._run_single_plugin()
        else:
            self._run_normal_mode()
            
    def _run_auto_mode(self):
        """Lance le mode automatique"""
        sequence_path = None
        sequence_data = None
        
        # Obtenir la séquence
        if self.args.shortcut:
            sequence_path, sequence_data = SequenceManager.find_sequence_by_shortcut(self.args.shortcut)
            if not sequence_path:
                sys.exit(1)
        elif self.args.sequence:
            sequence_path = self.args.sequence
            sequence_data = SequenceManager.load_sequence(sequence_path)
            if not sequence_data:
                sys.exit(1)
        else:
            logger.error("Le mode automatisé nécessite soit un fichier de séquence (--sequence) soit un shortcut (--shortcut)")
            sys.exit(1)
            
        # Vérifier la configuration
        auto_config = AutoConfig()
        plugins = sequence_data.get('plugins', [])
        plugin_instances = [(p['name'], 0) for p in plugins if isinstance(p, dict) and 'name' in p]
        config = auto_config.process_sequence(sequence_path, plugin_instances)
        
        # Créer une liste de tuples (nom, instance) avec des instances uniques
        plugin_instances = []
        instance_counters = {}
        for p in plugins:
            name = p['name']
            if name not in instance_counters:
                instance_counters[name] = 0
            plugin_instances.append((name, instance_counters[name]))
            instance_counters[name] += 1

        # Vérifier si tous les champs sont remplis
        all_fields_filled = True
        for plugin_id, plugin_config in config.items():
            if not plugin_config:
                all_fields_filled = False
                logger.warning(f"Configuration manquante pour {plugin_id}")
                break
            if not all(str(v).strip() for v in plugin_config.values()):
                all_fields_filled = False
                logger.warning(f"Configuration incomplète pour {plugin_id}: {plugin_config}")
                break
                
        # Lancer l'écran approprié
        if not all_fields_filled:
            logger.info("Configuration incomplète, ouverture de l'écran de configuration")
            class ConfigApp(App):
                def on_mount(self) -> None:
                    self.push_screen(PluginConfig(plugin_instances, sequence_file=sequence_path))
                    
            app = ConfigApp()
            app.run()
        else:
            logger.info(f"Configuration complète, lancement de l'exécution avec config: {config}")
            class AutoExecutionApp(App):
                def on_mount(self) -> None:
                    self.push_screen(ExecutionScreen(
                        plugins_config=config,
                        auto_execute=True
                    ))
                    
            app = AutoExecutionApp()
            app.run()
            
    def _run_single_plugin(self):
        """Lance l'exécution d'un plugin unique"""
        config = {}
        if self.args.config:
            config.update(ConfigLoader.load_config(self.args.config))
        if self.args.params:
            config.update(ConfigLoader.parse_params(self.args.params))
            
        plugins_config = {self.args.plugin: config}
        
        class ExecutionApp(App):
            def on_mount(self) -> None:
                self.push_screen(ExecutionScreen(plugins_config=plugins_config))
                
        app = ExecutionApp()
        app.run()
        
    def _run_normal_mode(self):
        """Lance l'interface normale"""
        app = Choice()
        app.run()
