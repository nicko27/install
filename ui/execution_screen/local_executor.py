"""
Module pour l'exécution locale des plugins.
"""

import os
import sys
import json
import asyncio
import logging
import traceback
from typing import Dict, Tuple
from ruamel.yaml import YAML

from ..utils.logging import get_logger
from ..utils.messaging import Message, MessageType, parse_message
from ..choice_screen.plugin_utils import get_plugin_folder_name
from .logger_utils import LoggerUtils
from .file_content_handler import FileContentHandler
from .root_credentials_manager import RootCredentialsManager

logger = get_logger('local_executor')

class LocalExecutor:
    """Classe pour l'exécution locale des plugins"""
    
    def __init__(self, app):
        self.app = app
        
    def log_message(self, message, level="info"):
        """Ajoute un message au log de l'application.
        
        Args:
            message (str): Le message à ajouter au log
            level (str): Le niveau de log (info, debug, error, success)
        """
        logger.debug(f"Ajout d'un message au log: {message} (niveau: {level})")
        try:
            # Utiliser LoggerUtils pour ajouter le message au log
            import asyncio
            
            # Créer une coroutine pour ajouter le message au log
            async def add_log_async():
                await LoggerUtils.add_log(self.app, message, level=level)
            
            # Exécuter la coroutine dans la boucle d'événements
            asyncio.create_task(add_log_async())
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout du message au log: {e}")
    
    async def execute_plugin(self, folder_name: str, config: dict) -> Tuple[bool, str]:
        """Exécute un plugin localement
        
        Args:
            folder_name: Le nom du dossier du plugin
            config: La configuration du plugin
            
        Returns:
            Tuple contenant le succès (bool) et la sortie (str)
        """
        try:
            logger.info(f"Exécution locale du plugin {folder_name}")
            
            # Construire le chemin du plugin
            plugin_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "plugins", folder_name)
            logger.debug(f"Chemin du plugin: {plugin_dir}")
            
            # Vérifier si c'est un plugin bash
            if os.path.exists(os.path.join(plugin_dir, "main.sh")):
                logger.info(f"Détecté comme plugin bash")
                is_bash_plugin = True
                exec_path = os.path.join(plugin_dir, "main.sh")
            else:
                # Sinon c'est un plugin Python
                exec_path = os.path.join(plugin_dir, "exec.py")
                logger.info(f"Détecté comme plugin Python")
                is_bash_plugin = False
                
            logger.debug(f"Chemin d'exécution: {exec_path}")
            logger.debug(f"Le fichier existe: {os.path.exists(exec_path)}")
            
            # Vérifier les paramètres du plugin (settings.yml)
            settings_path = os.path.join(plugin_dir, "settings.yml")
            plugin_settings = {}
            if os.path.exists(settings_path):
                try:
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        plugin_settings = YAML().load(f)
                    logger.debug(f"Paramètres du plugin chargés: {plugin_settings}")
                except Exception as e:
                    logger.error(f"Erreur lors de la lecture des paramètres du plugin: {e}")
                    logger.error(traceback.format_exc())
            
            # Vérifier si le plugin nécessite des droits root
            needs_root = False
            if plugin_settings and isinstance(plugin_settings, dict):
                needs_root = plugin_settings.get('local_root', False)
                logger.info(f"Plugin {folder_name} nécessite des droits root: {needs_root}")
            
            # Traiter le contenu des fichiers de configuration
            file_content = FileContentHandler.process_file_content(plugin_settings, config, plugin_dir)
            
            # Intégrer le contenu des fichiers dans la configuration
            for param_name, content in file_content.items():
                config[param_name] = content
                logger.info(f"Contenu du fichier intégré dans la configuration sous {param_name}")
            
            # Préparer la commande en fonction du type de plugin
            if is_bash_plugin:
                base_cmd = ["bash", exec_path, config.get('name', 'test'), config.get('intensity', 'light')]
            else:
                python_path = sys.executable if sys.executable.strip() else "/usr/bin/python3"
                base_cmd = [python_path, exec_path, json.dumps(config)]
            
            # Obtenir le gestionnaire d'identifiants root
            root_credentials_manager = RootCredentialsManager.get_instance()
            running_as_root = root_credentials_manager.is_running_as_root()
            
            # Déterminer comment exécuter la commande en fonction des besoins et de l'utilisateur actuel
            cmd = base_cmd
            
            if needs_root and not running_as_root:
                # Cas 1: Le plugin nécessite des droits root et nous ne sommes pas root
                password = root_credentials_manager.get_root_password()
                if password:
                    cmd = ["sudo", "-S"] + base_cmd
                else:
                    return False, "Mot de passe root requis mais non fourni"
            
            # Exécuter la commande
            logger.info(f"Exécution de la commande: {' '.join(cmd)}")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if needs_root and not running_as_root else None
            )
            
            # Gérer l'authentification si nécessaire
            if needs_root and not running_as_root and process.stdin:
                # Récupérer le mot de passe depuis le gestionnaire d'identifiants root
                password = root_credentials_manager.get_root_password()
                if password:
                    process.stdin.write(f"{password}\n".encode())
                    await process.stdin.drain()
                    logger.debug("Mot de passe sudo envoyé")
                else:
                    logger.warning("Aucun mot de passe sudo disponible, l'exécution pourrait échouer")
            
            # Lire la sortie de manière asynchrone pour un traitement en temps réel
            stdout_lines = []
            stderr_lines = []
            
            # Fonction pour lire un flux de manière asynchrone
            async def read_stream(stream, is_stderr=False):
                logger.debug(f"Stream reader started for {'stderr' if is_stderr else 'stdout'}")
                collected_lines = stderr_lines if is_stderr else stdout_lines
                counter = 0
                while True:
                    line = await stream.readline()
                    if not line:
                        logger.debug(f"Stream reader ending after {counter} lines")
                        break
                    counter += 1
                    line_decoded = line.decode().strip()
                    logger.debug(f"RAW LINE RECEIVED: {line_decoded}")
                    if line_decoded:
                        collected_lines.append(line_decoded)
                        
                        # Traiter la ligne pour les mises à jour en temps réel
                        if is_stderr:
                            logger.warning(f"STDERR: {line_decoded}")
                            # Ajouter les erreurs au log de l'application
                            self.log_message(f"[STDERR] {line_decoded}", level="error")
                        else:
                            logger.debug(f"STDOUT: {line_decoded}")
                            
                            # Essayer de traiter la ligne comme un message standardisé
                            try:
                                # Utiliser la méthode add_log_async pour ajouter le message au log
                                async def process_line_async():
                                    from ..utils.messaging import parse_message
                                    message_obj = parse_message(line_decoded)
                                    await LoggerUtils.display_message(self.app, message_obj)
                                
                                # Exécuter la coroutine dans la boucle d'événements
                                asyncio.create_task(process_line_async())
                            except Exception as e:
                                logger.error(f"Erreur lors du traitement de la ligne: {e}")
            
            # Lancer la lecture des flux stdout et stderr
            await asyncio.gather(
                read_stream(process.stdout),
                read_stream(process.stderr, True)
            )
            
            # Attendre la fin du processus
            exit_code = await process.wait()
            
            # Combiner les lignes en texte
            stdout_text = "\n".join(stdout_lines)
            stderr_text = "\n".join(stderr_lines)
            
            # Vérifier le code de retour
            if process.returncode != 0:
                error_msg = stderr_text if stderr_text else "Erreur inconnue (code retour non-zéro)"
                logger.error(f"Erreur lors de l'exécution du plugin {folder_name}: {error_msg}")
                return False, error_msg
            
            # Analyser la sortie pour détecter un format de retour spécifique
            # Certains plugins peuvent retourner un code 0 mais indiquer un échec dans leur sortie
            # Format attendu: "SUCCESS: message" ou "ERROR: message"
            if stdout_text:
                # Afficher toutes les lignes de stdout pour le débogage
                for line in stdout_text.splitlines():
                    if line.strip():
                        logger.debug(f"Plugin {folder_name} stdout: {line.strip()}")
                        # Traiter spécifiquement les lignes de débogage
                        if line.strip().startswith("DEBUG:"):
                            debug_msg = line.strip()[6:].strip()
                            logger.debug(f"Message de débogage du plugin {folder_name}: {debug_msg}")
                            # Ajouter ce message au log pour qu'il soit visible dans l'UI
                            self.log_message(f"[DEBUG] {debug_msg}", level="debug")
                
                # Traiter les lignes individuellement pour détecter les messages d'erreur
                for line in stdout_text.splitlines():
                    if line.strip().startswith("ERROR:"):
                        error_msg = line.strip()
                        logger.error(f"Plugin {folder_name} a signalé une erreur: {error_msg}")
                        # Ajouter ce message au log pour qu'il soit visible dans l'UI
                        self.log_message(f"[ERREUR] {error_msg[6:].strip()}", level="error")
                        return False, error_msg
                
                # Si aucune ligne individuelle ne commence par ERROR:, vérifier le texte complet
                if stdout_text.strip().startswith("ERROR:"):
                    error_msg = stdout_text.strip()
                    logger.error(f"Plugin {folder_name} a signalé une erreur: {error_msg}")
                    # Ajouter ce message au log pour qu'il soit visible dans l'UI
                    self.log_message(f"[ERREUR] {error_msg[6:].strip()}", level="error")
                    return False, error_msg
                
                # Vérifier si la sortie contient une indication de succès/échec au format JSON ou texte
                if "\"success\": False" in stdout_text or "'success': False" in stdout_text:
                    error_msg = stdout_text.strip()
                    logger.error(f"Plugin {folder_name} a signalé un échec dans sa sortie JSON: {error_msg}")
                    return False, error_msg
            
            # Succès
            logger.info(f"Plugin {folder_name} exécuté avec succès")
            
            # Vérifier si la sortie contient des messages de succès explicites
            if "SUCCESS:" in stdout_text:
                success_msg = next((line.strip() for line in stdout_text.splitlines() if "SUCCESS:" in line), None)
                if success_msg:
                    logger.info(f"Message de succès du plugin {folder_name}: {success_msg}")
                    # Ajouter ce message au log pour qu'il soit visible dans l'UI
                    self.log_message(f"[SUCCÈS] {success_msg[8:].strip()}", level="success")
            
            return True, stdout_text
            
        except Exception as e:
            logger.error(f"Erreur lors de l'exécution du plugin {folder_name}: {str(e)}")
            logger.error(traceback.format_exc())
            return False, str(e)

    async def run_local_plugin(self, app, plugin_id, plugin_widget, plugin_show_name, config, executed, total_plugins, result_queue):
        """Exécute un plugin localement"""
        try:
            # Extraire le nom du plugin pour les logs
            folder_name = plugin_widget.folder_name
            logger.info(f"Démarrage du plugin {folder_name} ({plugin_id})")

            # Initialiser la barre de progression
            plugin_widget.set_status('running')
            plugin_widget.update_progress(0.0, "Démarrage...")

            # Informer l'utilisateur du démarrage
            await LoggerUtils.add_log(app, f"Démarrage de {plugin_show_name}", "info")
            
            # Sauvegarder l'application pour pouvoir l'utiliser dans execute_plugin
            self.app = app

            # Construire le chemin du plugin
            plugin_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "plugins", folder_name)

            # Vérifier si c'est un plugin bash
            if os.path.exists(os.path.join(plugin_dir, "main.sh")):
                logger.info(f"Détecté comme plugin bash")
                is_bash_plugin = True
                exec_path = os.path.join(plugin_dir, "main.sh")
            else:
                # Sinon c'est un plugin Python
                exec_path = os.path.join(plugin_dir, "exec.py")
                logger.info(f"Détecté comme plugin Python")
                is_bash_plugin = False

            # Vérifier si le plugin nécessite des droits root
            needs_root = False
            if plugin_settings and isinstance(plugin_settings, dict):
                needs_root = plugin_settings.get('local_root', False)
                logger.info(f"Plugin {plugin_id} nécessite des droits root: {needs_root}")
            
            # Préparer la commande en fonction du type de plugin
            if is_bash_plugin:
                base_cmd = ["bash", exec_path, config.get('name', 'test'), config.get('intensity', 'light')]
            else:
                # Vérifier dans les paramètres de plugin (settings.yml)
                plugin_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "plugins", folder_name)
                settings_path = os.path.join(plugin_dir, "settings.yml")
                plugin_settings = {}
                if os.path.exists(settings_path):
                    try:
                        with open(settings_path, 'r', encoding='utf-8') as f:
                            plugin_settings = YAML().load(f)
                    except Exception as e:
                        logger.error(f"Erreur lors de la lecture des paramètres du plugin: {e}")
                
                # Traiter le contenu des fichiers de configuration
                file_content = FileContentHandler.process_file_content(plugin_settings, config, plugin_dir)
                
                # Intégrer le contenu des fichiers dans la configuration
                for param_name, content in file_content.items():
                    config[param_name] = content
                    logger.info(f"Contenu du fichier intégré dans la configuration sous {param_name}")
                
                # Afficher la structure de la configuration pour le débogage
                logger.debug(f"Structure de la configuration après ajout des fichiers: {list(config.keys())}")
                
                python_path = sys.executable if sys.executable.strip() else "/usr/bin/python3"
                # Afficher la configuration complète avant de l'envoyer au plugin
                logger.debug(f"Configuration complète envoyée au plugin: {list(config.keys())}")
                if 'printer_model_content' in config:
                    logger.debug(f"printer_model_content trouvé dans la configuration, type: {type(config['printer_model_content'])}")
                base_cmd = [python_path, exec_path, json.dumps(config)]
            # Obtenir le gestionnaire d'identifiants root
            root_credentials_manager = RootCredentialsManager.get_instance()
            running_as_root = root_credentials_manager.is_running_as_root()
            
            # Déterminer comment exécuter la commande en fonction des besoins et de l'utilisateur actuel
            cmd = base_cmd
            
            if needs_root and not running_as_root:
                # Cas 1: Le plugin nécessite des droits root et nous ne sommes pas root
                logger.info(f"Exécution du plugin {plugin_id} avec des droits root")
                
                # Récupérer les identifiants root
                root_credentials = root_credentials_manager.prepare_local_root_credentials(config)
                root_user = root_credentials.get('user', 'root')
                
                # Informer l'utilisateur de l'exécution en mode root
                root_msg = Message(
                    type=MessageType.INFO,
                    content=f"Exécution de {plugin_show_name} avec des droits root (utilisateur: {root_user})"
                )
                await LoggerUtils.display_message(app, root_msg)
                
                # Préparer la commande sudo
                cmd = ["sudo", "-S"] + base_cmd
                
            elif not needs_root and running_as_root:
                # Cas 2: Le plugin ne nécessite pas de droits root mais nous sommes déjà root
                # Récupérer l'utilisateur original
                sudo_user = root_credentials_manager.get_sudo_user()
                
                if sudo_user:
                    logger.info(f"Exécution du plugin {plugin_id} en tant qu'utilisateur {sudo_user} (déjà root)")
                    
                    # Informer l'utilisateur
                    user_msg = Message(
                        type=MessageType.INFO,
                        content=f"Exécution de {plugin_show_name} en tant qu'utilisateur {sudo_user}"
                    )
                    await LoggerUtils.display_message(app, user_msg)
                    
                    # Préparer la commande su
                    cmd = ["su", sudo_user, "-c", " ".join(str(arg) for arg in base_cmd)]
            
            elif needs_root and running_as_root:
                # Cas 3: Le plugin nécessite des droits root et nous sommes déjà root
                logger.info(f"Exécution du plugin {plugin_id} avec des droits root (déjà root)")
                root_msg = Message(
                    type=MessageType.INFO,
                    content=f"Exécution de {plugin_show_name} avec des droits root (déjà root)"
                )
                await LoggerUtils.display_message(app, root_msg)
                # Pas besoin de modifier la commande, nous sommes déjà root
            
            logger.info(f"Commande à exécuter : {cmd}")

            # Créer le processus de manière asynchrone
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if needs_root else None,  # Ajouter stdin pour sudo
                cwd=plugin_dir
            )
            
            # Gérer l'authentification si nécessaire
            running_as_root = root_credentials_manager.is_running_as_root()
            
            # Cas 1: Nous ne sommes pas root mais le plugin nécessite des droits root
            if needs_root and not running_as_root and process.stdin:
                # Récupérer le mot de passe depuis le gestionnaire d'identifiants root
                root_credentials = root_credentials_manager.get_local_root_credentials()
                
                if root_credentials and root_credentials.get('password'):
                    sudo_password = root_credentials.get('password')
                    process.stdin.write(f"{sudo_password}\n".encode())
                    await process.stdin.drain()
                    logger.debug("Mot de passe sudo envoyé")
                else:
                    logger.warning("Aucun mot de passe sudo disponible, l'exécution pourrait échouer")
                    warning_msg = Message(
                        type=MessageType.WARNING,
                        content="Aucun mot de passe sudo disponible, l'exécution pourrait échouer"
                    )
                    await LoggerUtils.display_message(app, warning_msg)
            
            # Cas 2: Nous sommes root mais le plugin ne nécessite pas de droits root
            # Dans ce cas, su ne demande pas de mot de passe car nous sommes déjà root

            # Lire la sortie de manière asynchrone
            async def read_stream(stream, is_error=False):
                logger.debug(f"Stream reader started for {'stderr' if is_error else 'stdout'}")
                counter = 0
                while True:
                    line = await stream.readline()
                    if not line:
                        logger.debug(f"Stream reader ending after {counter} lines")
                        break
                    counter += 1
                    line_decoded = line.decode().strip()
                    logger.debug(f"RAW LINE RECEIVED: {line_decoded}")
                    if line_decoded:
                        # Si c'est un message de débogage, l'ignorer
                        if line_decoded.startswith("DEBUG:"):
                            logger.debug(line_decoded)
                            continue
                        # Traiter la ligne avec LoggerUtils.process_output_line qui gère déjà le parsing des messages
                        processed = await LoggerUtils.process_output_line(app, line_decoded, plugin_widget, executed, total_plugins)
                        logger.debug(f"Ligne traitée: {processed}")
            # Lancer la lecture des flux stdout et stderr
            # Utiliser asyncio.create_task pour permettre l'exécution parallèle et la mise à jour de la progression
            stdout_task = asyncio.create_task(read_stream(process.stdout))
            stderr_task = asyncio.create_task(read_stream(process.stderr, True))
            
            # Attendre la fin du processus tout en vérifiant périodiquement la progression
            while process.returncode is None:
                # Vérifier l'état du processus
                try:
                    exit_code = await asyncio.wait_for(process.wait(), timeout=0.1)
                    break
                except asyncio.TimeoutError:
                    # Le processus est toujours en cours d'exécution
                    pass
                    
            # Attendre que les tâches de lecture des flux soient terminées
            await stdout_task
            await stderr_task
            
            # Récupérer le code de sortie
            exit_code = process.returncode

            # Traiter le résultat
            if exit_code == 0:
                success_msg = Message(
                    type=MessageType.SUCCESS,
                    content=f"{plugin_show_name} terminé(e) avec succès"
                )
                await LoggerUtils.display_message(app, success_msg)
                plugin_widget.set_status('success')
                await result_queue.put((True, "Exécution terminée avec succès"))
            else:
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"{plugin_show_name}: Erreur lors de l'exécution (code {exit_code})"
                )
                await LoggerUtils.display_message(app, error_msg)
                plugin_widget.set_status('error', f"Erreur (code {exit_code})")
                await result_queue.put((False, f"Erreur lors de l'exécution (code {exit_code})"))

        except Exception as e:
            error_msg = f"Erreur lors de l'exécution: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            
            # Envoyer l'erreur aux logs
            error_obj = Message(
                type=MessageType.ERROR,
                content=error_msg
            )
            await LoggerUtils.display_message(app, error_obj)
            
            await result_queue.put((False, error_msg))

    @staticmethod
    def update_global_progress(app, progress: float):
        """Mise à jour de la progression globale"""
        progress_bar = app.query_one("#global-progress")
        if progress_bar:
            progress_bar.update(total=100.0, progress=progress * 100)