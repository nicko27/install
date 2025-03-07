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

    @staticmethod
    async def run_local_plugin(app, plugin_id, plugin_widget, plugin_show_name, config, executed, total_plugins, result_queue):
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
                root_msg = Message(MessageType.INFO, f"Exécution de {plugin_show_name} avec des droits root (utilisateur: {root_user})")
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
                    user_msg = Message(MessageType.INFO, f"Exécution de {plugin_show_name} en tant qu'utilisateur {sudo_user}")
                    await LoggerUtils.display_message(app, user_msg)
                    
                    # Préparer la commande su
                    cmd = ["su", sudo_user, "-c", " ".join(str(arg) for arg in base_cmd)]
            
            elif needs_root and running_as_root:
                # Cas 3: Le plugin nécessite des droits root et nous sommes déjà root
                logger.info(f"Exécution du plugin {plugin_id} avec des droits root (déjà root)")
                root_msg = Message(MessageType.INFO, f"Exécution de {plugin_show_name} avec des droits root (déjà root)")
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
                    warning_msg = Message(MessageType.WARNING, "Aucun mot de passe sudo disponible, l'exécution pourrait échouer")
                    await LoggerUtils.display_message(app, warning_msg)
            
            # Cas 2: Nous sommes root mais le plugin ne nécessite pas de droits root
            # Dans ce cas, su ne demande pas de mot de passe car nous sommes déjà root

            # Lire la sortie de manière asynchrone
            async def read_stream(stream, is_error=False):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    line = line.decode().strip()
                    if line:
                        # Traiter la ligne avec le nouveau système de gestion des messages
                        await LoggerUtils.process_output_line(app, line, plugin_widget, executed, total_plugins)

            # Lancer la lecture des flux stdout et stderr
            await asyncio.gather(
                read_stream(process.stdout),
                read_stream(process.stderr, True)
            )

            # Attendre la fin du processus
            exit_code = await process.wait()

            # Traiter le résultat
            if exit_code == 0:
                success_msg = Message(MessageType.SUCCESS, f"{plugin_show_name} terminé(e) avec succès")
                await LoggerUtils.display_message(app, success_msg)
                plugin_widget.set_status('success')
                await result_queue.put((True, "Exécution terminée avec succès"))
            else:
                error_msg = Message(MessageType.ERROR, f"{plugin_show_name}: Erreur lors de l'exécution (code {exit_code})")
                await LoggerUtils.display_message(app, error_msg)
                plugin_widget.set_status('error', f"Erreur (code {exit_code})")
                await result_queue.put((False, f"Erreur lors de l'exécution (code {exit_code})"))

        except Exception as e:
            error_msg = f"Erreur lors de l'exécution: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            
            # Envoyer l'erreur aux logs
            error_obj = Message(MessageType.ERROR, error_msg)
            await LoggerUtils.display_message(app, error_obj)
            
            await result_queue.put((False, error_msg))

    @staticmethod
    def update_global_progress(app, progress: float):
        """Mise à jour de la progression globale"""
        progress_bar = app.query_one("#global-progress")
        if progress_bar:
            progress_bar.update(total=100.0, progress=progress * 100)