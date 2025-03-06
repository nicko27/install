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

from ..utils.logging import get_logger
from ..utils.messaging import Message, MessageType, parse_message
from ..choice_screen.plugin_utils import get_plugin_folder_name
from .logger_utils import LoggerUtils

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

            # Préparer la commande en fonction du type de plugin
            if is_bash_plugin:
                cmd = ["bash", exec_path, config.get('name', 'test'), config.get('intensity', 'light')]
            else:
                python_path = sys.executable if sys.executable.strip() else "/usr/bin/python3"
                cmd = [python_path, exec_path, json.dumps(config)]
            logger.info(f"Commande à exécuter : {cmd}")

            # Créer le processus de manière asynchrone
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=plugin_dir
            )

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