"""
Module pour l'exécution locale des plugins.
"""

import os
import sys
import json
import re
import asyncio
import threading
from typing import Dict, Tuple
import traceback

from .logger_utils import LoggerUtils
from ..choice_management.plugin_utils import get_plugin_folder_name
from ..logging import get_logger

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

            # Obtenir le nom du dossier du plugin
            folder_name = get_plugin_folder_name(plugin_id)

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
                        await LocalExecutor.handle_output(app, line, plugin_widget, executed, total_plugins)

            # Lancer la lecture des flux stdout et stderr
            await asyncio.gather(
                read_stream(process.stdout),
                read_stream(process.stderr, True)
            )

            # Attendre la fin du processus
            exit_code = await process.wait()

            # Traiter le résultat
            if exit_code == 0:
                await LoggerUtils.add_log(app, f"{plugin_show_name} terminé(e) avec succès")
                plugin_widget.set_status('success')
                await result_queue.put((True, "Exécution terminée avec succès"))
            else:
                error_msg = f"Erreur lors de l'exécution (code {exit_code})"
                plugin_widget.set_status('error', error_msg)
                await LoggerUtils.add_log(app, f"{plugin_show_name}: {error_msg}", 'error')
                await result_queue.put((False, error_msg))

        except Exception as e:
            error_msg = f"Erreur lors de l'exécution: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            await result_queue.put((False, error_msg))

    @staticmethod
    async def handle_output(app, line: str, plugin_widget, executed, total_plugins):
        """Gère les logs et la progression d'un plugin"""
        try:
            # Ignorer les lignes vides
            if not line:
                return

            line = line.strip()
            if not line:
                return

            # Parser le format standard [timestamp] [level] message
            match = re.match(r'\[(.*?)\] \[(\w+)\] (.*)', line)
            if match:
                timestamp, level, message = match.groups()
                level = level.lower()

                # Gérer la progression si présente
                if "Progression :" in message:
                    progress_match = re.search(r'Progression : (\d+)% \(étape (\d+)/(\d+)\)', message)
                    if progress_match:
                        try:
                            # Récupérer et valider les valeurs
                            progress = float(progress_match.group(1)) / 100.0  # Convertir en fraction
                            current_step = int(progress_match.group(2))
                            total_steps = int(progress_match.group(3))

                            # Vérifier que les valeurs sont valides
                            if 0 <= progress <= 1 and current_step <= total_steps:
                                step_text = f"Étape {current_step}/{total_steps}"

                                # Mettre à jour la barre de progression du plugin
                                plugin_widget.update_progress(progress, step_text)

                                # Mettre à jour la progression globale
                                global_progress = (executed + progress) / total_plugins
                                LocalExecutor.update_global_progress(app, global_progress)

                            return  # Ne pas ajouter aux logs
                        except Exception as e:
                            # Si l'analyse de la progression échoue, continuer avec le message normal
                            logger.error(f"Erreur lors de l'analyse de la progression: {str(e)}")

                # Traiter les autres types de messages
                if level in ['error', 'warning', 'info', 'debug', 'success']:
                    # Pour les erreurs et warnings, mettre à jour le statut
                    if level in ['error', 'warning']:
                        await LocalExecutor.sync_ui(
                            app,
                            plugin_widget,
                            executed,
                            total_plugins,
                            status='error' if level == 'error' else 'warning',
                            message=message,
                            log_entry=line
                        )
                    else:
                        await LocalExecutor.sync_ui(app, plugin_widget, executed, total_plugins, log_entry=line)
            else:
                # Ligne sans format standard, l'afficher telle quelle
                # Vérifier s'il s'agit d'une erreur de permission
                if "permission denied" in line.lower() or "error" in line.lower():
                    await LocalExecutor.sync_ui(
                        app,
                        plugin_widget,
                        executed,
                        total_plugins,
                        status='error',
                        message="Erreur de permission",
                        log_entry=f"[ERROR] {line}"
                    )
                else:
                    await LocalExecutor.sync_ui(app, plugin_widget, executed, total_plugins, log_entry=line)

        except Exception as e:
            logger.error(f"Erreur dans handle_output: {str(e)}")
            # Tenter de logger le message brut
            try:
                await LoggerUtils.add_log(app, f"Message non traité: {repr(line)}", 'error')
            except:
                pass

    @staticmethod
    async def sync_ui(app, plugin_widget, executed, total_plugins, progress=None, step=None, status=None, message=None, log_entry=None):
        """Synchronise l'interface utilisateur avec les mises à jour du plugin"""
        try:
            # Mettre à jour la progression si spécifiée
            if progress is not None:
                # Vérifier si nous sommes dans le thread principal
                if app._thread_id == threading.get_ident():
                    # Dans le thread principal, appeler directement
                    plugin_widget.update_progress(progress, step)
                else:
                    # Dans un thread différent, utiliser call_from_thread
                    await app.call_from_thread(plugin_widget.update_progress, progress, step)
                # Mettre à jour la progression globale
                global_progress = (executed + progress) / total_plugins
                await app.call_from_thread(LocalExecutor.update_global_progress, app, global_progress)

            # Mettre à jour le statut si spécifié
            if status is not None:
                if app._thread_id == threading.get_ident():
                    plugin_widget.set_status(status, message)
                else:
                    await app.call_from_thread(plugin_widget.set_status, status, message)

            # Mettre à jour les logs si spécifié
            if log_entry is not None:
                if app._thread_id == threading.get_ident():
                    resultat= log_entry.split(' ')
                    level = resultat[2].lower().replace("[","").replace("]", "")
                    message = ' '.join(resultat[3:])
                    # Dans le thread principal
                    await LoggerUtils.add_log(app, message, level)
                else:
                    # Dans un thread différent
                    await app.call_from_thread(LoggerUtils.add_log, app, log_entry)

        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'UI: {str(e)}")

    @staticmethod
    def update_global_progress(app, progress: float):
        """Mise à jour de la progression globale"""
        progress_bar = app.query_one("#global-progress")
        if progress_bar:
            progress_bar.update(total=100.0, progress=progress * 100)