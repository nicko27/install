import os
import sys
import json
import asyncio
import logging
import traceback
from typing import Dict, Tuple
from ruamel.yaml import YAML

# Assuming these imports are correctly placed relative to local_executor.py
from ..utils.logging import get_logger
from ..utils.messaging import Message, MessageType, parse_message
from ..choice_screen.plugin_utils import get_plugin_folder_name
from .logger_utils import LoggerUtils
from .file_content_handler import FileContentHandler

logger = get_logger('local_executor')

class LocalExecutor:
    """Classe pour l'exécution locale des plugins"""

    def __init__(self, app=None):
        self.app = app

    def log_message(self, message, level="info", target_ip=None):
        """Ajoute un message au log de l'application.

        Args:
            message (str): Le message à ajouter au log
            level (str): Le niveau de log (info, debug, error, success)
            target_ip (str, optional): Adresse IP cible pour les plugins SSH
        """
        logger.debug(f"Ajout d'un message au log: {message} (niveau: {level}, ip: {target_ip})")
        try:
            # Utiliser LoggerUtils pour ajouter le message au log
            import asyncio

            # Créer une coroutine pour ajouter le message au log
            async def add_log_async():
                await LoggerUtils.add_log(self.app, message, level=level, target_ip=target_ip)

            # Exécuter la coroutine dans la boucle d'événements
            # Vérifier si une boucle est déjà en cours d'exécution
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(add_log_async())
            except RuntimeError: # Pas de boucle en cours (peut arriver dans certains contextes)
                 # Fallback : essayer de l'exécuter de manière synchrone ou le logger
                 logger.warning("Aucune boucle asyncio en cours pour log_message, log direct.")
                 # Vous pourriez vouloir logger différemment ici ou l'ignorer
                 print(f"LOG [{level.upper()}]: {message}") # Log simple en fallback

        except Exception as e:
            logger.error(f"Erreur lors de l'ajout du message au log: {e}")

    async def execute_plugin(self, plugin_widget, folder_name: str, config: dict) -> Tuple[bool, str]:
        """Exécute un plugin localement

        Args:
            plugin_widget: Le widget Textual représentant le plugin (peut être None).
            folder_name: Le nom du dossier du plugin.
            config: La configuration du plugin.

        Returns:
            Tuple contenant le succès (bool) et la sortie (str).
        """
        stdout_text = "" # Initialiser pour le bloc finally
        stderr_text = "" # Initialiser pour le bloc finally
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

            # Traiter le contenu des fichiers de configuration
            file_content = FileContentHandler.process_file_content(plugin_settings, config, plugin_dir)

            # Intégrer le contenu des fichiers dans la configuration
            # S'assurer que le contenu n'est ajouté que sous config et pas à la racine
            if 'config' in config and isinstance(config['config'], dict):
                for param_name, content in file_content.items():
                    # Ajouter le contenu uniquement dans le dictionnaire config
                    config['config'][param_name] = content
                    logger.info(f"Contenu du fichier intégré dans config.{param_name}")
            else:
                # Fallback si config n'est pas un dictionnaire
                for param_name, content in file_content.items():
                    config[param_name] = content
                    logger.info(f"Contenu du fichier intégré dans la configuration sous {param_name}")

            # Préparer la commande en fonction du type de plugin
            if is_bash_plugin:
                base_cmd = ["bash", exec_path, config.get('name', 'test'), config.get('intensity', 'light')]
                logger.debug(f"Commande bash: {' '.join(base_cmd)}")
            else:
                python_path = sys.executable if sys.executable and sys.executable.strip() else "/usr/bin/python3"
                base_cmd = [python_path, exec_path, json.dumps(config)]
                logger.debug(f"Commande Python: {' '.join(base_cmd)}")

            # Exécuter la commande
            logger.info(f"Exécution de la commande: {' '.join(base_cmd)}")
            process = await asyncio.create_subprocess_exec(
                *base_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Lire la sortie de manière asynchrone pour un traitement en temps réel
            stdout_lines = []
            stderr_lines = []

            # Fonction pour lire un flux de manière asynchrone
            async def read_stream(stream, is_stderr=False):
                logger.debug(f"Stream reader started for {'stderr' if is_stderr else 'stdout'}")
                collected_lines = stderr_lines if is_stderr else stdout_lines
                counter = 0
                while True:
                    try:
                        line = await stream.readline()
                        if not line:
                            logger.debug(f"Stream reader ending after {counter} lines (EOF)")
                            break
                    except Exception as read_err:
                        logger.error(f"Erreur lors de la lecture du stream {'stderr' if is_stderr else 'stdout'}: {read_err}")
                        break # Arrêter la lecture en cas d'erreur

                    counter += 1
                    line_decoded = line.decode(errors='replace').strip() # Remplacer les erreurs de décodage
                    logger.debug(f"RAW LINE RECEIVED ({'stderr' if is_stderr else 'stdout'}): {line_decoded}")
                    if line_decoded:
                        collected_lines.append(line_decoded)

                        try:
                            # Essayer de parser la ligne comme JSON
                            log_entry = json.loads(line_decoded)

                            if is_stderr:
                                # Pour stderr, toujours traiter comme une erreur
                                error_msg = log_entry.get('message', line_decoded)
                                logger.error(f"Erreur du plugin (stderr JSON): {error_msg}")
                                self.log_message(error_msg, level="error", target_ip=None)
                            else:
                                if self.app:
                                    # Pour stdout, traiter normalement via LoggerUtils
                                    await LoggerUtils.process_output_line(
                                        self.app,
                                        line_decoded,  # Passer la ligne JSON complète
                                        plugin_widget,
                                        target_ip=None,
                                        is_priority=True # Prioriser messages du plugin actif
                                    )
                        except json.JSONDecodeError:
                            # Fallback pour les lignes non-JSON
                            if is_stderr:
                                logger.error(f"Erreur du plugin (stderr TEXT): {line_decoded}")
                                self.log_message(line_decoded, level="error", target_ip=None)
                            else:
                                if self.app:
                                    await LoggerUtils.process_output_line(
                                        self.app,
                                        line_decoded, # Passer la ligne texte brute
                                        plugin_widget,
                                        target_ip=None,
                                        is_priority=True # Prioriser messages du plugin actif
                                    )

            # Lancer la lecture des flux stdout et stderr et attendre qu'ils se terminent
            await asyncio.gather(
                read_stream(process.stdout),
                read_stream(process.stderr, True)
            )

            # Attendre la fin du processus
            exit_code = await process.wait()
            logger.info(f"Plugin {folder_name} terminé avec le code de sortie: {exit_code}")

            # Combiner les lignes en texte (pour le retour de fonction)
            stdout_text = "\n".join(stdout_lines)
            stderr_text = "\n".join(stderr_lines)

            # --- Flush LoggerUtils avant de retourner le résultat ---
            logger.debug("Flushing pending LoggerUtils messages before returning...")
            if self.app:
                try:
                    await LoggerUtils.flush_pending_messages(self.app)
                    logger.debug("LoggerUtils flush complete.")
                except Exception as flush_err:
                    logger.error(f"Erreur lors du flush de LoggerUtils: {flush_err}")
            # --- Fin du Flush ---

            # Vérifier le code de retour
            if exit_code != 0:
                error_msg = stderr_text if stderr_text else f"Erreur inconnue (code retour {exit_code})"
                logger.error(f"Erreur lors de l'exécution du plugin {folder_name}: {error_msg}")

                # Récupérer l'IP cible si elle existe dans le widget
                target_ip = getattr(plugin_widget, 'target_ip', None) if plugin_widget else None
                # Ajouter un message d'erreur dans les logs de l'interface (déjà fait dans read_stream, mais redondance OK)
                self.log_message(
                    f"Erreur lors de l'exécution du plugin {folder_name} (code: {exit_code}): {error_msg}",
                    level="error",
                    target_ip=target_ip
                )

                return False, error_msg

            # Analyser la sortie pour détecter un format de retour spécifique (même si code retour 0)
            if stdout_text:
                # Afficher toutes les lignes de stdout pour le débogage
                for line in stdout_lines: # Utiliser stdout_lines car stdout_text peut être modifié
                    if line.strip():
                        logger.debug(f"Plugin {folder_name} stdout line: {line.strip()}")
                        # Traiter spécifiquement les lignes de débogage du plugin
                        if line.strip().startswith("DEBUG:"):
                            debug_msg = line.strip()[6:].strip()
                            logger.debug(f"Message de débogage du plugin {folder_name}: {debug_msg}")
                            target_ip = getattr(plugin_widget, 'target_ip', None) if plugin_widget else None
                            self.log_message(f"[DEBUG] {debug_msg}", level="debug", target_ip=target_ip)

                # Traiter les lignes individuellement pour détecter les messages d'erreur
                for line in stdout_lines:
                    if line.strip().startswith("ERROR:"):
                        error_msg = line.strip()
                        logger.error(f"Plugin {folder_name} a signalé une erreur: {error_msg}")
                        target_ip = getattr(plugin_widget, 'target_ip', None) if plugin_widget else None
                        self.log_message(f"[ERREUR] {error_msg[6:].strip()}", level="error", target_ip=target_ip)
                        # Pas besoin de flush ici car déjà fait avant le return
                        return False, error_msg # Retourner échec si ERROR: trouvé

                # Si aucune ligne individuelle ne commence par ERROR:, vérifier le texte complet (moins courant)
                if stdout_text.strip().startswith("ERROR:"):
                    error_msg = stdout_text.strip()
                    logger.error(f"Plugin {folder_name} a signalé une erreur: {error_msg}")
                    target_ip = getattr(plugin_widget, 'target_ip', None) if plugin_widget else None
                    self.log_message(f"[ERREUR] {error_msg[6:].strip()}", level="error", target_ip=target_ip)
                    # Pas besoin de flush ici car déjà fait avant le return
                    return False, error_msg

                # Vérifier si la sortie contient une indication d'échec au format JSON
                if "\"success\": false" in stdout_text.lower() or "'success': false" in stdout_text.lower():
                    error_msg = stdout_text.strip()
                    logger.error(f"Plugin {folder_name} a signalé un échec dans sa sortie JSON: {error_msg}")
                    # Pas besoin de flush ici car déjà fait avant le return
                    return False, error_msg # Retourner échec

            # Vérifier si la sortie contient des termes d'erreur génériques (dernier recours)
            has_error_in_output = any([
                "[error]" in stdout_text.lower(),
                "error:" in stdout_text.lower() and "no error:" not in stdout_text.lower(),
                "exception:" in stdout_text.lower(),
                "traceback (most recent call last)" in stdout_text.lower()
            ])

            if has_error_in_output:
                error_msg = "Des erreurs génériques ont été détectées dans la sortie du plugin."
                logger.error(f"Plugin {folder_name} a généré des erreurs dans sa sortie: {error_msg}\n---SORTIE---\n{stdout_text}\n------------")
                target_ip = getattr(plugin_widget, 'target_ip', None) if plugin_widget else None
                self.log_message(f"[ERREUR] {error_msg}", level="error", target_ip=target_ip)
                # Pas besoin de flush ici car déjà fait avant le return
                return False, stdout_text # Retourner la sortie complète comme message d'erreur

            # Succès
            logger.info(f"Plugin {folder_name} exécuté avec succès.")

            # Vérifier si la sortie contient des messages de succès explicites
            if "SUCCESS:" in stdout_text:
                success_msg = next((line.strip() for line in stdout_lines if "SUCCESS:" in line), None)
                if success_msg:
                    logger.info(f"Message de succès du plugin {folder_name}: {success_msg}")
                    target_ip = getattr(plugin_widget, 'target_ip', None) if plugin_widget else None
                    self.log_message(f"[SUCCÈS] {success_msg[8:].strip()}", level="success", target_ip=target_ip)

            # Pas besoin de flush ici car déjà fait avant le return
            return True, stdout_text

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Erreur lors de l'exécution du plugin {folder_name}: {error_msg}")
            logger.error(traceback.format_exc())

            # Récupérer l'IP cible si elle existe dans le widget
            target_ip = getattr(plugin_widget, 'target_ip', None) if plugin_widget else None

            # Ajouter un message d'erreur dans les logs de l'interface
            try:
                self.log_message(
                    f"Erreur lors de l'exécution du plugin {folder_name}: {error_msg}",
                    level="error",
                    target_ip=target_ip
                )
            except Exception as log_error:
                logger.error(f"Erreur lors de l'ajout du message d'erreur aux logs: {log_error}")

            # --- Flush LoggerUtils même en cas d'exception ---
            logger.debug("Flushing pending LoggerUtils messages after exception...")
            if self.app:
                try:
                    await LoggerUtils.flush_pending_messages(self.app)
                    logger.debug("LoggerUtils flush complete after exception.")
                except Exception as flush_err:
                    logger.error(f"Error flushing LoggerUtils after exception: {flush_err}")
            # --- Fin du Flush ---

            return False, error_msg

    @staticmethod
    def update_global_progress(app, progress: float):
        """Mise à jour de la progression globale"""
        # S'assurer que progress est bien entre 0 et 1
        progress = max(0.0, min(1.0, progress))
        try:
            progress_bar = app.query_one("#global-progress")
            if progress_bar:
                # Mettre à jour la barre de progression
                # Utiliser total=1.0 car progress est déjà entre 0 et 1
                progress_bar.update(total=1.0, progress=progress)
                logger.debug(f"Global progress updated to {progress*100:.1f}%")
        except Exception as e:
            logger.debug(f"Could not update global progress bar: {e}")