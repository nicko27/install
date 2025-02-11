from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Label, Button, ProgressBar, Footer
from textual.reactive import reactive
import asyncio
import os
from datetime import datetime
import json
import sys
import logging
import logging.handlers

# Configuration du logging de débogage
debug_log_handler = logging.handlers.RotatingFileHandler(
    '/media/nico/Drive/install/logs/debug.log',
    maxBytes=1024*1024,  # 1 Mo
    backupCount=3
)
debug_log_handler.setLevel(logging.DEBUG)
debug_log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
debug_log_handler.setFormatter(debug_log_formatter)

# Ajouter le handler au logger racine
root_logger = logging.getLogger()
root_logger.addHandler(debug_log_handler)

logger = root_logger

class PluginExecutionContainer(Container):
    """Container for plugin execution status and logs"""
    
    def __init__(self, plugin: dict, config: dict, instance_number: int = 1, **kwargs):
        super().__init__(**kwargs)
        self.plugin = plugin
        self.config = config
        self.plugin_id = plugin['plugin']
        self.instance_number = instance_number
        self.status = "En attente"
        self.process = None
        self.show_logs = False
        self.log_callback = None

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        with Horizontal(classes="plugin-header"):
            yield Label(f"{self.plugin['name']} (Instance {self.instance_number})", id=f"plugin_name_{self.plugin_id}_{self.instance_number}")
            yield Label("En attente", id=f"status_{self.plugin_id}_{self.instance_number}")
        
        yield ProgressBar(
            id=f"progress_{self.plugin_id}_{self.instance_number}", 
            total=100,
            show_eta=False,
            show_percentage=True
        )
        
        # Un seul conteneur de logs pour tous les plugins
        yield Label("", id="central_logs")

    async def execute(self, config: dict):
        """
        Execute the plugin with the given configuration
        
        Args:
            config (dict): Configuration for the plugin
        """
        try:
            # Récupérer le chemin du script du plugin
            plugin_script = self.plugin.get('script', '')
            if not plugin_script:
                raise ValueError(f"Aucun script trouvé pour le plugin {self.plugin_id}")
            
            # Préparer les arguments
            args = [plugin_script]
            
            # Ajouter les arguments de configuration
            if isinstance(config, dict):
                # Si config est un dictionnaire, convertir en JSON
                args.append(json.dumps(config))
            elif isinstance(config, str):
                # Si config est une chaîne, l'ajouter directement
                args.append(config)
            elif config is not None:
                # Convertir en chaîne si possible
                args.append(str(config))
            
            # Logs de débogage
            logger.debug(f"Exécution du plugin {self.plugin_id} avec arguments : {args}")
            
            # Créer le processus
            process = await asyncio.create_subprocess_exec(
                sys.executable,  # Utiliser l'interpréteur Python actuel
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy()
            )
            
            # Stocker le processus pour un éventuel arrêt ultérieur
            self.process = process
            
            # Récupérer les widgets pour les mises à jour
            status_label = self.query_one(f"#status_{self.plugin_id}_{self.instance_number}", Label)
            progress_bar = self.query_one(f"#progress_{self.plugin_id}_{self.instance_number}", ProgressBar)
            central_logs = self.query_one("#central_logs", Label)
            
            # Mettre à jour le statut
            self.status = "En cours"
            status_label.update(self.status)
            
            # Lire la sortie
            while True:
                try:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    line = line.decode().strip()
                    
                    # Check for progress update
                    if line.startswith('PROGRESS:'):
                        try:
                            progress = int(line.split(':')[1])
                            progress_bar.progress = progress
                        except (IndexError, ValueError):
                            pass
                    else:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        log_entry = f"[{timestamp}] {self.plugin['name']}: {line}"
                        
                        # Mise à jour des logs centraux
                        current_logs = central_logs.renderable
                        if isinstance(current_logs, str):
                            central_logs.update(f"{current_logs}\n{log_entry}")
                        else:
                            central_logs.update(log_entry)
                        
                        # Callback optionnel
                        if self.log_callback:
                            self.log_callback(self.plugin['name'], line)
                except Exception as e:
                    logger.error(f"Error reading output: {e}")
                    break
            
            # Wait for completion
            stdout, stderr = await process.communicate()
            
            # Update status based on return code
            if process.returncode == 0:
                self.status = "Terminé"
                status_label.update(self.status)
                progress_bar.progress = 100
                timestamp = datetime.now().strftime("%H:%M:%S")
                log_entry = f"[{timestamp}] [green]{self.plugin['name']}: Exécution terminée avec succès[/green]"
                
                # Mise à jour des logs centraux
                current_logs = central_logs.renderable
                if isinstance(current_logs, str):
                    central_logs.update(f"{current_logs}\n{log_entry}")
                else:
                    central_logs.update(log_entry)
                
                if self.log_callback:
                    self.log_callback(self.plugin['name'], "Exécution terminée avec succès")
            else:
                self.status = "Erreur"
                status_label.update(self.status)
                timestamp = datetime.now().strftime("%H:%M:%S")
                log_entry = f"[{timestamp}] [red]{self.plugin['name']}: Erreur lors de l'exécution (code {process.returncode})[/red]"
                
                # Mise à jour des logs centraux
                current_logs = central_logs.renderable
                if isinstance(current_logs, str):
                    central_logs.update(f"{current_logs}\n{log_entry}")
                else:
                    central_logs.update(log_entry)
                
                if self.log_callback:
                    self.log_callback(self.plugin['name'], f"Erreur lors de l'exécution (code {process.returncode})")
                
                if stderr:
                    error_log_entry = f"[{timestamp}] [red]{self.plugin['name']}: {stderr.decode().strip()}[/red]"
                    current_logs = central_logs.renderable
                    if isinstance(current_logs, str):
                        central_logs.update(f"{current_logs}\n{error_log_entry}")
                    else:
                        central_logs.update(error_log_entry)
                    
                    if self.log_callback:
                        self.log_callback(self.plugin['name'], stderr.decode().strip())
                
        except Exception as e:
            logger.exception(f"Error executing plugin {self.plugin_id}: {e}")
            self.status = "Erreur"
            status_label = self.query_one(f"#status_{self.plugin_id}_{self.instance_number}", Label)
            status_label.update(self.status)
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = f"[{timestamp}] [red]{self.plugin['name']}: Erreur: {str(e)}[/red]"
            
            # Mise à jour des logs centraux
            central_logs = self.query_one("#central_logs", Label)
            current_logs = central_logs.renderable
            if isinstance(current_logs, str):
                central_logs.update(f"{current_logs}\n{log_entry}")
            else:
                central_logs.update(log_entry)
            
            if self.log_callback:
                self.log_callback(self.plugin['name'], str(e))

class PluginExecution(Screen):
    """Plugin execution screen"""
    
    BINDINGS = [
        ("esc", "quit", "Quitter"),
        ("l", "toggle_logs", "Logs"),
    ]
    
    CSS_PATH = os.path.join(os.path.dirname(__file__), "styles/execution.css")
    
    def __init__(self, plugins: list, configs: dict):
        super().__init__()
        self.plugins = plugins
        self.configs = configs
        self.containers = []  # Liste au lieu d'un dictionnaire pour gérer les instances multiples
        self.show_logs = False

    def compose(self) -> ComposeResult:
        """Create the plugin execution screen"""
        # En-tête fixe avec les contrôles et la progression globale
        with Container(id="fixed-header"):
            yield Label("Exécution des plugins", id="title")
            
            # Controls
            with Horizontal(classes="controls-section"):
                start_button = Button("Démarrer", id="start", variant="primary")
                start_button.disabled = False
                yield start_button
                
                stop_button = Button("Arrêter", id="stop", variant="error")
                stop_button.disabled = True
                yield stop_button
            
            # Global progress
            with Vertical(classes="progress-section"):
                yield Label("Progression globale", classes="progress-label")
                yield ProgressBar(
                    id="global-progress",
                    show_eta=False,
                    show_percentage=True,
                    total=100
                )
        
        # Conteneur défilant pour les plugins
        with ScrollableContainer(id="plugins-container"):
            # Plugin containers
            for plugin in self.plugins:
                plugin_id = plugin['plugin']
                configs = self.configs.get(plugin_id, [])
                
                # Créer un conteneur pour chaque instance de configuration
                for idx, config in enumerate(configs, 1):
                    container = PluginExecutionContainer(
                        plugin=plugin,
                        config=config,
                        instance_number=idx if len(configs) > 1 else 1,
                        classes="plugin-execution"
                    )
                    self.containers.append(container)
                    yield container
        
        # Conteneur de logs centralisé (masqué par défaut)
        with Vertical(id="logs-container", classes="hidden"):
            yield Label("Logs centralisés", classes="logs-title")
            yield Label("", id="central_logs", classes="central-logs")
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Configurer les événements de logs centralisés"""
        for container in self.containers:
            container.log_callback = self.update_central_logs
    
    def update_central_logs(self, plugin_name: str, log_message: str) -> None:
        """Mettre à jour les logs centralisés"""
        central_logs = self.query_one("#central_logs")
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {plugin_name}: {log_message}"
        
        # Mise à jour de l'affichage
        current_logs = central_logs.renderable
        if isinstance(current_logs, str):
            central_logs.update(f"{current_logs}\n{log_entry}")
        else:
            central_logs.update(log_entry)
        
        # Logging de débogage
        logger.debug(log_entry)
    
    def action_toggle_logs(self) -> None:
        """Basculer la visibilité des logs"""
        logs_container = self.query_one("#logs-container")
        if self.show_logs:
            logs_container.add_class("hidden")
            self.show_logs = False
        else:
            logs_container.remove_class("hidden")
            self.show_logs = True
    
    async def start_execution(self) -> None:
        """Start executing all plugins"""
        # Notify start
        self.notify("Démarrage de l'exécution des plugins", severity="information")
        
        # Get global progress bar
        global_progress = self.query_one("#global-progress")
        total_plugins = len(self.containers)
        completed_plugins = 0
        
        # Exécuter les plugins en séquence
        for container in self.containers:
            # Exécuter le plugin avec sa configuration
            await container.execute(container.config)
            
            # Update global progress
            completed_plugins += 1
            global_progress.progress = int((completed_plugins / total_plugins) * 100)
        
        # Notify completion
        self.notify(
            "Exécution terminée",
            severity="success",
            timeout=5
        )
            
    def stop_execution(self) -> None:
        """Stop all plugin executions"""
        for container in self.containers:
            if container.process:
                container.process.terminate()
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "start":
            # Disable start button and enable stop button
            start_button = self.query_one("#start", Button)
            start_button.disabled = True
            
            stop_button = self.query_one("#stop", Button)
            stop_button.disabled = False
            
            # Start execution
            asyncio.create_task(self.start_execution())
            
        elif event.button.id == "stop":
            # Stop execution
            self.stop_execution()
            
            # Enable start button and disable stop button
            start_button = self.query_one("#start", Button)
            start_button.disabled = False
            
            stop_button = self.query_one("#stop", Button)
            stop_button.disabled = True
            
    def action_quit(self) -> None:
        """Handle escape key"""
        self.app.pop_screen()
