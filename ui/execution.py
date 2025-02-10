from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Label, Button, ProgressBar, Footer
from textual.reactive import reactive
import asyncio
import os
from datetime import datetime

from .utils import setup_logging

logger = setup_logging()

class PluginExecutionContainer(Container):
    """Container for plugin execution status and logs"""
    
    def __init__(self, plugin: dict, config: dict, **kwargs):
        super().__init__(**kwargs)
        self.plugin = plugin
        self.config = config
        self.plugin_id = plugin['plugin']
        self.status = "En attente"
        self.process = None
        
    def compose(self) -> ComposeResult:
        """Create child widgets"""
        # Plugin header
        with Horizontal(classes="plugin-header"):
            yield Label(f"{self.plugin['icon']} {self.plugin['name']}", classes="plugin-title")
            yield Label(self.status, id=f"status_{self.plugin_id}", classes="plugin-status")
            
        # Progress bar
        yield ProgressBar(
            total=100,
            id=f"progress_{self.plugin_id}",
            show_eta=False,
            show_percentage=True
        )
        
        # Log output
        yield Label("", id=f"log_{self.plugin_id}", classes="log-output")
        
    async def execute(self, config: dict) -> None:
        """Execute the plugin with the given configuration"""
        try:
            # Get widget references
            log = self.query_one(f"#log_{self.plugin_id}")
            status_label = self.query_one(f"#status_{self.plugin_id}")
            progress_bar = self.query_one(f"#progress_{self.plugin_id}")
            
            # Build command
            cmd = ['python', os.path.join('plugins', self.plugin_id, 'main.py')]
            
            # Set up environment
            env = os.environ.copy()
            # Convert config dict to environment variables
            timestamp = datetime.now().strftime("%H:%M:%S")
            log.write(f"[{timestamp}] Variables d'environnement:")
            for key, value in config.items():
                env_key = key.upper()
                env[env_key] = str(value)
                log.write(f"[{timestamp}]   {env_key}={value}")
            
            # Update status
            self.status = "En cours d'exécution"
            status_label.update(self.status)
            
            # Execute plugin
            timestamp = datetime.now().strftime("%H:%M:%S")
            log.write(f"[{timestamp}] [blue]Démarrage de l'exécution...[/blue]")
            log.write(f"[{timestamp}] Commande: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            self.process = process
            
            # Read output
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
                        log.write(f"[{timestamp}] {line}")
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
                log.write(f"[{timestamp}] [green]Exécution terminée avec succès[/green]")
            else:
                self.status = "Erreur"
                status_label.update(self.status)
                timestamp = datetime.now().strftime("%H:%M:%S")
                log.write(f"[{timestamp}] [red]Erreur lors de l'exécution (code {process.returncode})[/red]")
                if stderr:
                    log.write(f"[{timestamp}] [red]{stderr.decode().strip()}[/red]")
                    
        except Exception as e:
            logger.exception(f"Error executing plugin {self.plugin_id}: {e}")
            self.status = "Erreur"
            status_label.update(self.status)
            timestamp = datetime.now().strftime("%H:%M:%S")
            log.write(f"[{timestamp}] [red]Erreur: {str(e)}[/red]")

class PluginExecution(Screen):
    """Plugin execution screen"""
    
    BINDINGS = [
        ("esc", "quit", "Quitter"),
    ]
    
    CSS_PATH = os.path.join(os.path.dirname(__file__), "styles/execution.css")
    
    def __init__(self, plugins: list, configs: dict):
        super().__init__()
        self.plugins = plugins
        self.configs = configs
        self.containers = {}
        
    def compose(self) -> ComposeResult:
        """Create the plugin execution screen"""
        yield Label("Exécution des plugins", id="title")
        
        with ScrollableContainer(id="execution-container"):
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
                yield ProgressBar(id="global-progress", show_eta=False)
            
            # Plugin containers
            for plugin in self.plugins:
                container = PluginExecutionContainer(
                    plugin=plugin,
                    config=self.configs.get(plugin['plugin'], {}),
                    classes="plugin-execution"
                )
                self.containers[plugin['plugin']] = container
                yield container
                
        yield Footer()
    
    async def start_execution(self) -> None:
        """Start executing all plugins"""
        # Notify start
        self.notify("Démarrage de l'exécution des plugins", severity="information")
        
        # Exécuter les plugins en séquence
        for plugin_id, container in self.containers.items():
            # Récupérer la configuration
            config = self.configs.get(plugin_id, {})
            
            # Exécuter le plugin
            await container.execute(config)
        
        # Notify completion
        self.notify(
            "Exécution terminée",
            severity="success",
            timeout=5
        )
            
    def stop_execution(self) -> None:
        """Stop all plugin executions"""
        for container in self.containers.values():
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
