import os
import sys
import time
import subprocess
import threading
import traceback
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Union
from datetime import datetime
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Label, Button, TextLog
from textual.widget import Widget

from ..choice_screen.plugin_utils import get_plugin_folder_name
from ..utils.logging import get_logger

logger = get_logger('execution_screen')

class ExecutionScreen(App):
    """
    Écran d'exécution des plugins sélectionnés.
    
    Cette classe gère l'exécution séquentielle des plugins sélectionnés
    et l'affichage des résultats.
    """
    
    BINDINGS = [
        ("escape", "quit", "Quitter"),
    ]
    
    CSS_PATH = "../styles/execution.tcss"
    
    def __init__(
        self, 
        plugins: List, 
        plugins_config: Optional[Dict[str, Dict[str, Any]]] = None,
        auto_execute: bool = False
    ):
        """
        Initialise l'écran d'exécution.
        
        Args:
            plugins: Liste des plugins à exécuter (tuples ou PluginInstance)
            plugins_config: Configuration des plugins par clé unique (par défaut: None)
            auto_execute: Lancer automatiquement l'exécution (par défaut: False)
        """
        super().__init__()
        self.plugins = plugins
        self.plugins_config = plugins_config or {}
        self.auto_execute = auto_execute
        self.current_plugin_idx = -1
        self.execution_thread = None
        self.execution_running = False
        self.execution_results = {}
        logger.debug(f"Initialisation de l'écran d'exécution avec {len(plugins)} plugins")
    
    def compose(self) -> ComposeResult:
        """
        Compose l'interface d'exécution.
        
        Returns:
            ComposeResult: Résultat de la composition
        """
        with Vertical(id="execution-container"):
            with Horizontal(id="execution-header"):
                yield Label("Exécution des plugins", id="execution-title")
                yield Label("", id="plugin-status")
            
            # Journal d'exécution
            yield TextLog(id="execution-log", highlight=True, wrap=True)
            
            # Boutons d'action
            with Horizontal(id="execution-buttons"):
                yield Button("Exécuter", id="start-execution", variant="primary")
                yield Button("Arrêter", id="stop-execution", variant="error", disabled=True)
                yield Button("Fermer", id="close-execution")
    
    def on_mount(self) -> None:
        """
        Actions effectuées au montage de l'écran.
        """
        logger.debug("Montage de l'écran d'exécution")
        
        # Récupérer le journal d'exécution
        self.log = self.query_one("#execution-log", TextLog)
        
        # Mettre à jour le statut
        self._update_status("Prêt à exécuter")
        
        # Si auto_execute est activé, lancer l'exécution
        if self.auto_execute:
            self.start_execution()
    
    def _update_status(self, status: str) -> None:
        """
        Met à jour le statut d'exécution.
        
        Args:
            status: Texte du statut
        """
        status_label = self.query_one("#plugin-status", Label)
        status_label.update(status)
    
    def _log_message(self, message: str, level: str = "info") -> None:
        """
        Ajoute un message au journal d'exécution.
        
        Args:
            message: Message à ajouter
            level: Niveau de log (info, warning, error, success)
        """
        # Ajouter un préfixe selon le niveau
        prefix = ""
        if level == "info":
            prefix = "[INFO] "
        elif level == "warning":
            prefix = "[WARN] "
        elif level == "error":
            prefix = "[ERROR] "
        elif level == "success":
            prefix = "[SUCCESS] "
        
        # Ajouter l'horodatage
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Formater le message
        formatted_message = f"[{timestamp}] {prefix}{message}"
        
        # Ajouter au journal
        self.log.write(formatted_message, level)
        
        # Logger également
        if level == "info":
            logger.info(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "error":
            logger.error(message)
        elif level == "success":
            logger.info(message)
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Gère les clics sur les boutons.
        
        Args:
            event: Événement de bouton pressé
        """
        button_id = event.button.id
        
        if button_id == "start-execution":
            await self.start_execution()
        elif button_id == "stop-execution":
            await self.stop_execution()
        elif button_id == "close-execution":
            await self.action_quit()
    
    async def start_execution(self) -> None:
        """
        Démarre l'exécution des plugins.
        """
        if self.execution_running:
            self._log_message("Exécution déjà en cours", "warning")
            return
        
        # Filtrer les plugins pour ne garder que ceux qui ne sont pas des séquences
        filtered_plugins = []
        for plugin in self.plugins:
            # Vérifier si c'est un tuple ou une instance
            if isinstance(plugin, tuple):
                plugin_name = plugin[0]
                if not plugin_name.startswith('__sequence__'):
                    filtered_plugins.append(plugin)
            else:  # Si c'est un PluginInstance
                if not plugin.is_sequence:
                    filtered_plugins.append(plugin)
        
        # Vérifier s'il reste des plugins à exécuter
        if not filtered_plugins:
            self._log_message("Aucun plugin à exécuter", "warning")
            return
        
        # Initialiser l'exécution
        self.execution_running = True
        self.current_plugin_idx = -1
        self.execution_results = {}
        
        # Mettre à jour les boutons
        start_button = self.query_one("#start-execution", Button)
        stop_button = self.query_one("#stop-execution", Button)
        start_button.disabled = True
        stop_button.disabled = False
        
        # Démarrer le thread d'exécution
        self._log_message("Démarrage de l'exécution des plugins", "info")
        self.execution_thread = threading.Thread(
            target=self._execute_plugins_thread,
            args=(filtered_plugins,)
        )
        self.execution_thread.daemon = True
        self.execution_thread.start()
    
    def _execute_plugins_thread(self, plugins: List) -> None:
        """
        Exécute les plugins dans un thread séparé.
        
        Args:
            plugins: Liste des plugins à exécuter
        """
        try:
            # Exécuter chaque plugin
            for i, plugin in enumerate(plugins):
                # Vérifier si l'exécution a été arrêtée
                if not self.execution_running:
                    self._log_message("Exécution arrêtée", "warning")
                    break
                
                # Mettre à jour l'index courant
                self.current_plugin_idx = i
                
                # Extraire les informations du plugin
                if isinstance(plugin, tuple):
                    plugin_name = plugin[0]
                    instance_id = plugin[1]
                    plugin_config = plugin[2] if len(plugin) > 2 else {}
                else:  # Si c'est un PluginInstance
                    plugin_name = plugin.name
                    instance_id = plugin.instance_id
                    plugin_config = plugin.config
                
                # Créer une clé unique pour ce plugin
                plugin_key = f"{plugin_name}_{instance_id}"
                
                # Récupérer la configuration depuis plugins_config si disponible
                if plugin_key in self.plugins_config:
                    plugin_config.update(self.plugins_config[plugin_key])
                
                # Mettre à jour le statut
                self._update_plugin_status(i + 1, len(plugins), plugin_name)
                
                # Exécuter le plugin
                self._log_message(f"Exécution du plugin {plugin_name} (ID: {instance_id})", "info")
                
                try:
                    # Exécuter le plugin et récupérer le résultat
                    result = self._execute_plugin(plugin_name, plugin_config)
                    
                    # Stocker le résultat
                    self.execution_results[plugin_key] = result
                    
                    if result['success']:
                        self._log_message(f"Plugin {plugin_name} exécuté avec succès", "success")
                    else:
                        self._log_message(f"Échec de l'exécution du plugin {plugin_name}: {result['message']}", "error")
                        
                        # Arrêter l'exécution en cas d'erreur si auto_execute est activé
                        if self.auto_execute:
                            self._log_message("Arrêt de l'exécution suite à une erreur", "warning")
                            self.execution_running = False
                            break
                except Exception as e:
                    self._log_message(f"Erreur lors de l'exécution du plugin {plugin_name}: {str(e)}", "error")
                    self._log_message(traceback.format_exc(), "error")
                    
                    # Arrêter l'exécution en cas d'erreur si auto_execute est activé
                    if self.auto_execute:
                        self._log_message("Arrêt de l'exécution suite à une erreur", "warning")
                        self.execution_running = False
                        break
            
            # Fin de l'exécution
            self._log_message("Exécution terminée", "info")
        
        except Exception as e:
            self._log_message(f"Erreur lors de l'exécution: {str(e)}", "error")
            self._log_message(traceback.format_exc(), "error")
        
        finally:
            # Réinitialiser l'état
            self.execution_running = False
            
            # Mettre à jour les boutons (dans le thread principal)
            def update_buttons():
                start_button = self.query_one("#start-execution", Button)
                stop_button = self.query_one("#stop-execution", Button)
                start_button.disabled = False
                stop_button.disabled = True
                self._update_status("Exécution terminée")
            
            self.call_from_thread(update_buttons)
    
    def _update_plugin_status(self, current: int, total: int, plugin_name: str) -> None:
        """
        Met à jour le statut d'exécution du plugin.
        
        Args:
            current: Index du plugin en cours
            total: Nombre total de plugins
            plugin_name: Nom du plugin en cours
        """
        status_text = f"Exécution {current}/{total}: {plugin_name}"
        
        # Mettre à jour dans le thread principal
        def update_status():
            self._update_status(status_text)
        
        self.call_from_thread(update_status)
    
    def _execute_plugin(self, plugin_name: str, plugin_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Exécute un plugin spécifique.
        
        Args:
            plugin_name: Nom du plugin à exécuter
            plugin_config: Configuration du plugin
            
        Returns:
            Dict[str, Any]: Résultat de l'exécution
        """
        result = {
            'success': False,
            'message': "",
            'output': "",
            'start_time': time.time(),
            'end_time': None,
            'duration': 0
        }
        
        try:
            # Obtenir le chemin du dossier du plugin
            plugin_folder = get_plugin_folder_name(plugin_name)
            plugin_path = Path('plugins') / plugin_folder
            
            # Vérifier si le plugin existe
            if not plugin_path.exists():
                result['message'] = f"Le dossier du plugin n'existe pas: {plugin_path}"
                return result
            
            # Déterminer le script d'exécution (Python ou Bash)
            exec_py_path = plugin_path / 'exec.py'
            exec_bash_path = plugin_path / 'exec.bash'
            
            if exec_py_path.exists():
                # Exécuter le script Python
                self._log_message(f"Exécution du script Python: {exec_py_path}", "info")
                result = self._execute_python_script(exec_py_path, plugin_config)
            elif exec_bash_path.exists():
                # Exécuter le script Bash
                self._log_message(f"Exécution du script Bash: {exec_bash_path}", "info")
                result = self._execute_bash_script(exec_bash_path, plugin_config)
            else:
                result['message'] = f"Aucun script d'exécution trouvé pour le plugin {plugin_name}"
            
            # Calculer la durée
            result['end_time'] = time.time()
            result['duration'] = result['end_time'] - result['start_time']
            
        except Exception as e:
            result['message'] = str(e)
            result['end_time'] = time.time()
            result['duration'] = result['end_time'] - result['start_time']
            self._log_message(f"Erreur lors de l'exécution du plugin {plugin_name}: {str(e)}", "error")
            self._log_message(traceback.format_exc(), "error")
        
        return result
    
    def _execute_python_script(self, script_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Exécute un script Python.
        
        Args:
            script_path: Chemin du script Python
            config: Configuration à passer au script
            
        Returns:
            Dict[str, Any]: Résultat de l'exécution
        """
        result = {
            'success': False,
            'message': "",
            'output': "",
            'start_time': time.time(),
            'end_time': None,
            'duration': 0
        }
        
        try:
            # Créer un fichier temporaire pour la configuration
            config_file = Path('temp_config.yml')
            with open(config_file, 'w', encoding='utf-8') as f:
                import yaml
                yaml.dump(config, f)
            
            # Construire la commande
            python_executable = sys.executable
            command = [python_executable, str(script_path), str(config_file)]
            
            # Exécuter la commande
            self._log_message(f"Exécution de la commande: {' '.join(command)}", "info")
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            # Lire la sortie standard et d'erreur
            stdout_lines = []
            stderr_lines = []
            
            # Lire la sortie standard
            for line in process.stdout:
                line = line.strip()
                if line:
                    stdout_lines.append(line)
                    self._log_message(f"[STDOUT] {line}", "info")
            
            # Lire la sortie d'erreur
            for line in process.stderr:
                line = line.strip()
                if line:
                    stderr_lines.append(line)
                    self._log_message(f"[STDERR] {line}", "error")
            
            # Attendre la fin du processus
            return_code = process.wait()
            
            # Nettoyer le fichier temporaire
            if config_file.exists():
                config_file.unlink()
            
            # Vérifier le code de retour
            if return_code == 0:
                result['success'] = True
                result['message'] = "Script exécuté avec succès"
            else:
                result['message'] = f"Le script a retourné une erreur (code {return_code})"
            
            # Stocker la sortie
            result['output'] = "\n".join(stdout_lines + stderr_lines)
            
        except Exception as e:
            result['message'] = str(e)
            self._log_message(f"Erreur lors de l'exécution du script Python: {str(e)}", "error")
            self._log_message(traceback.format_exc(), "error")
        
        return result
    
    def _execute_bash_script(self, script_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Exécute un script Bash.
        
        Args:
            script_path: Chemin du script Bash
            config: Configuration à passer au script
            
        Returns:
            Dict[str, Any]: Résultat de l'exécution
        """
        result = {
            'success': False,
            'message': "",
            'output': "",
            'start_time': time.time(),
            'end_time': None,
            'duration': 0
        }
        
        try:
            # Créer un fichier temporaire pour la configuration
            config_file = Path('temp_config.yml')
            with open(config_file, 'w', encoding='utf-8') as f:
                import yaml
                yaml.dump(config, f)
            
            # Rendre le script exécutable
            os.chmod(script_path, 0o755)
            
            # Construire la commande
            command = [str(script_path), str(config_file)]
            
            # Exécuter la commande
            self._log_message(f"Exécution de la commande: {' '.join(command)}", "info")
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                shell=True
            )
            
            # Lire la sortie standard et d'erreur
            stdout_lines = []
            stderr_lines = []
            
            # Lire la sortie standard
            for line in process.stdout:
                line = line.strip()
                if line:
                    stdout_lines.append(line)
                    self._log_message(f"[STDOUT] {line}", "info")
            
            # Lire la sortie d'erreur
            for line in process.stderr:
                line = line.strip()
                if line:
                    stderr_lines.append(line)
                    self._log_message(f"[STDERR] {line}", "error")
            
            # Attendre la fin du processus
            return_code = process.wait()
            
            # Nettoyer le fichier temporaire
            if config_file.exists():
                config_file.unlink()
            
            # Vérifier le code de retour
            if return_code == 0:
                result['success'] = True
                result['message'] = "Script exécuté avec succès"
            else:
                result['message'] = f"Le script a retourné une erreur (code {return_code})"
            
            # Stocker la sortie
            result['output'] = "\n".join(stdout_lines + stderr_lines)
            
        except Exception as e:
            result['message'] = str(e)
            self._log_message(f"Erreur lors de l'exécution du script Bash: {str(e)}", "error")
            self._log_message(traceback.format_exc(), "error")
        
        return result
    
    async def stop_execution(self) -> None:
        """
        Arrête l'exécution des plugins.
        """
        if not self.execution_running:
            self._log_message("Aucune exécution en cours", "warning")
            return
        
        # Arrêter l'exécution
        self.execution_running = False
        self._log_message("Arrêt de l'exécution en cours...", "warning")
        
        # Mettre à jour les boutons
        start_button = self.query_one("#start-execution", Button)
        stop_button = self.query_one("#stop-execution", Button)
        start_button.disabled = False
        stop_button.disabled = True
        
        # Attendre la fin du thread
        if self.execution_thread and self.execution_thread.is_alive():
            self.execution_thread.join(timeout=2.0)
            if self.execution_thread.is_alive():
                self._log_message("Le thread d'exécution ne répond pas", "error")
    
    async def action_quit(self) -> None:
        """
        Quitte l'écran d'exécution.
        """
        # Arrêter l'exécution si nécessaire
        if self.execution_running:
            await self.stop_execution()
        
        # Retourner à l'écran précédent
        self.app.pop_screen()