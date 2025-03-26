"""
Module pour l'exécution SSH des plugins.
"""

import os
import sys
import json
import asyncio
import logging
import traceback
import time
from typing import Dict, Tuple, Optional, Any, List
from ruamel.yaml import YAML
from pathlib import Path

from ..utils.logging import get_logger
from .logger_utils import LoggerUtils
from .file_content_handler import FileContentHandler
from .root_credentials_manager import RootCredentialsManager
from .file_content_handler import FileContentHandler
from ..ssh_manager.ssh_config_loader import SSHConfigLoader
from ..ssh_manager.ip_utils import get_target_ips

import paramiko

logger = get_logger('ssh_executor')

# Configuration du logging
# Créer le répertoire des logs
LOGS_DIR = '/tmp/pcUtils/logs'


# Constantes
DEFAULT_SSH_PORT = 22
DEFAULT_TEMP_DIR_PERMISSIONS = 0o755
TEMP_DIR_PREFIX = "pcUtils_"
TEMP_FILE_PREFIX = "pcUtils_"

# Noms de fichiers et dossiers
PLUGIN_EXEC_FILE = 'exec.py'
SSH_WRAPPER_FILE = 'ssh_wrapper.py'
LOADING_UTILS_DIR = 'loading_utils'
CONFIG_FILE = 'config.json'
WRAPPER_CONFIG_FILE = 'wrapper_config.json'
PLUGINS_DIR = 'plugins'
# LOGS_DIR est défini plus haut

# Messages d'erreur
ERROR_MESSAGES = {
    'no_root_creds': "Identifiants root SSH manquants dans la configuration",
    'no_target_ips': "Aucune adresse IP cible spécifiée dans la configuration",
    'no_ssh_creds': "Identifiants SSH manquants dans la configuration globale et du plugin",
    'plugin_copy_failed': "Échec de la copie des fichiers du plugin",
    'wrapper_copy_failed': "Échec de la copie du script wrapper",
    'config_creation_failed': "Échec de la création de la configuration",
    'execution_failed': "Échec sur au moins une machine"
}

class SSHExecutor:
    """Classe pour l'exécution des plugins via SSH"""
    
    def __init__(self, config: Dict):
        """
        Initialise l'exécuteur SSH.
        
        Args:
            config: Configuration complète du plugin
        """
        self.config = config
        self.plugin_config = config.get('config', {})
        self.plugin_name = config.get('plugin_name')
        self.instance_id = config.get('instance_id', 0)
        self.ssh_debug = config.get('ssh_debug', False)  # Récupérer depuis la config principale
        self.temp_dir = None
        self.ssh = None
        self.sftp = None
        self.root_credentials_manager = RootCredentialsManager.get_instance()
        
    def _get_excluded_files(self, plugin_settings: Dict) -> List[str]:
        """Récupère la liste des fichiers à exclure"""
        excluded = []
        if isinstance(plugin_settings, dict):
            for section in ['exceptions', 'excluded_files', 'ssh_pattern_exceptions']:
                value = plugin_settings.get(section, [])
                if isinstance(value, str):
                    excluded.append(value)
                elif isinstance(value, list):
                    excluded.extend(value)
        return list(set(filter(None, excluded)))

    async def _copy_plugin_files(self, sftp, plugin_path, temp_dir):
        """Copie les fichiers du plugin vers le répertoire temporaire"""
        try:
            # Vérifier/créer le répertoire temporaire
            if not self._ensure_temp_dir(sftp, temp_dir):
                return False
            
            # Copier le dossier loading_utils s'il existe
            loading_utils_path = os.path.join(os.path.dirname(plugin_path), LOADING_UTILS_DIR)
            if os.path.exists(loading_utils_path):
                remote_loading_utils = os.path.join(temp_dir, LOADING_UTILS_DIR)
                if not self._ensure_remote_dir(sftp, remote_loading_utils):
                    return False
                
                if not self._copy_directory_contents(sftp, loading_utils_path, remote_loading_utils):
                    return False
            
            # Copier les fichiers du plugin
            if not self._copy_directory_contents(sftp, plugin_path, temp_dir):
                return False
            
            # Vérifier que exec.py a été copié
            exec_path = os.path.join(temp_dir, PLUGIN_EXEC_FILE)
            try:
                sftp.stat(exec_path)
                logger.debug(f"{PLUGIN_EXEC_FILE} a été copié avec succès")
                return True
            except FileNotFoundError:
                logger.error(f"{PLUGIN_EXEC_FILE} n'a pas été copié")
                return False
            
        except Exception as e:
            logger.error(f"Erreur lors de la copie des fichiers: {e}")
            return False

    def _ensure_temp_dir(self, sftp, temp_dir):
        """Assure que le répertoire temporaire existe avec les bonnes permissions"""
        try:
            sftp.stat(temp_dir)
            logger.debug(f"Le répertoire temporaire {temp_dir} existe déjà")
            return True
        except FileNotFoundError:
            try:
                sftp.mkdir(temp_dir)
                logger.debug(f"Répertoire temporaire {temp_dir} créé avec succès")
                return True
            except Exception as e:
                logger.error(f"Erreur lors de la création du répertoire temporaire: {e}")
                return False

    def _ensure_remote_dir(self, sftp, remote_dir):
        """Assure que le répertoire distant existe"""
        try:
            sftp.mkdir(remote_dir)
            logger.debug(f"Dossier distant créé: {remote_dir}")
            return True
        except Exception as e:
            logger.debug(f"Le dossier distant {remote_dir} existe peut-être déjà: {e}")
            return True

    def _copy_directory_contents(self, sftp, local_path, remote_path, plugin_settings=None):
        """Copie le contenu d'un répertoire en tenant compte des exclusions
        
        Args:
            sftp: Session SFTP
            local_path: Chemin local à copier
            remote_path: Chemin distant cible
            plugin_settings: Paramètres du plugin (pour les exclusions)
            
        Returns:
            bool: True si la copie a réussi, False sinon
        """
        try:
            # Récupérer la liste des fichiers à exclure
            excluded_files = []
            if plugin_settings:
                excluded_files = self._get_excluded_files(plugin_settings)
            
            # Toujours exclure settings.yml
            if 'settings.yml' not in excluded_files:
                excluded_files.append('settings.yml')
                
            logger.debug(f"Fichiers exclus: {excluded_files}")
            
            # Parcourir les fichiers/dossiers du répertoire
            for item in os.listdir(local_path):
                local_item = os.path.join(local_path, item)
                remote_item = os.path.join(remote_path, item)
                
                # Vérifier si le fichier est à exclure
                if item in excluded_files or any(self._match_pattern(item, pattern) for pattern in excluded_files):
                    logger.debug(f"Exclusion de {local_item} selon les règles d'exclusion")
                    continue
                    
                try:
                    if os.path.isfile(local_item):
                        sftp.put(local_item, remote_item)
                        logger.debug(f"Fichier copié: {local_item} -> {remote_item}")
                    elif os.path.isdir(local_item):
                        if not self._ensure_remote_dir(sftp, remote_item):
                            return False
                        if not self._copy_directory_contents(sftp, local_item, remote_item, plugin_settings):
                            return False
                except Exception as e:
                    logger.error(f"Erreur lors de la copie de {local_item}: {e}")
                    return False
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la copie du répertoire {local_path}: {e}")
            return False

    def _match_pattern(self, filename, pattern):
        """Vérifie si un nom de fichier correspond à un motif d'exclusion
        
        Args:
            filename: Nom du fichier à vérifier
            pattern: Motif d'exclusion (peut contenir *)
            
        Returns:
            bool: True si le fichier correspond au motif
        """
        import fnmatch
        return fnmatch.fnmatch(filename, pattern)

    def _create_and_send_config_file(self, sftp, config_data, temp_dir, filename):
        """Crée et envoie un fichier de configuration"""
        timestamp = int(time.time())
        local_config = os.path.join(TEMP_FILE_PREFIX, f"{filename}_{timestamp}.json")
        remote_config = os.path.join(temp_dir, f"{filename}.json")
        
        try:
            # Créer le fichier local
            with open(local_config, 'w', encoding='utf-8') as f:
                json.dump(config_data, f)
            logger.debug(f"Fichier de configuration {filename} créé localement: {local_config}")
            
            # Copier vers le serveur distant
            sftp.put(local_config, remote_config)
            logger.debug(f"Fichier de configuration {filename} copié vers le serveur: {remote_config}")
            
            # Nettoyer le fichier local
            try:
                os.remove(local_config)
            except Exception as e:
                logger.warning(f"Impossible de supprimer le fichier temporaire local {filename}: {e}")
            
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la gestion du fichier de configuration {filename}: {e}")
            return False

    async def _execute_on_single_host(self, host: str, ssh_config: Dict) -> Tuple[bool, str]:
        """Exécute le plugin sur un hôte spécifique"""
        try:
            # Récupérer les informations de connexion
            user = ssh_config.get('user')
            password = ssh_config.get('password')
            port = ssh_config.get('port', DEFAULT_SSH_PORT)
            
            if not user or not password:
                return False, "Informations de connexion SSH manquantes"
            
            # Créer le répertoire temporaire
            temp_dir = f"/tmp/{TEMP_DIR_PREFIX}{int(time.time())}"
            
            # Utiliser asyncio pour exécuter les opérations SSH de manière asynchrone
            # Créer une tâche pour la connexion SSH
            loop = asyncio.get_event_loop()
            
            # Se connecter à l'hôte (opération bloquante exécutée dans un thread)
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            await loop.run_in_executor(
                None, 
                lambda: ssh.connect(host, port=port, username=user, password=password)
            )
            
            try:
                # Créer le répertoire temporaire sur la machine distante (opération bloquante)
                stdin, stdout, stderr = await loop.run_in_executor(
                    None,
                    lambda: ssh.exec_command(f"mkdir -p {temp_dir}")
                )
                
                # Vérifier le statut de la commande (opération bloquante)
                exit_status = await loop.run_in_executor(
                    None,
                    lambda: stderr.channel.recv_exit_status()
                )
                
                if exit_status != 0:
                    error_msg = await loop.run_in_executor(
                        None,
                        lambda: stderr.read().decode()
                    )
                    return False, f"Erreur lors de la création du répertoire temporaire: {error_msg}"
                
                # Ouvrir la session SFTP (opération bloquante)
                sftp = await loop.run_in_executor(
                    None,
                    lambda: ssh.open_sftp()
                )
                
                # Copier les fichiers du plugin
                plugins_base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'plugins')
                plugin_dir = os.path.join(plugins_base_dir, self.plugin_name)
                
                # Copier le plugin lui-même
                await loop.run_in_executor(
                    None,
                    lambda: self._copy_directory_contents(sftp, plugin_dir, temp_dir)
                )
                
                # Copier le module loading_utils qui est partagé entre les plugins
                loading_utils_dir = os.path.join(plugins_base_dir, 'loading_utils')
                remote_loading_utils_dir = os.path.join(temp_dir, 'loading_utils')
                
                # Créer le répertoire loading_utils sur la machine distante
                try:
                    await loop.run_in_executor(
                        None,
                        lambda: self._ensure_remote_dir(sftp, remote_loading_utils_dir)
                    )
                    
                    # Copier le contenu du module loading_utils
                    await loop.run_in_executor(
                        None,
                        lambda: self._copy_directory_contents(sftp, loading_utils_dir, remote_loading_utils_dir)
                    )
                    logger.debug(f"Module loading_utils copié vers {remote_loading_utils_dir}")
                except Exception as e:
                    logger.error(f"Erreur lors de la copie du module loading_utils: {e}")
                    raise

                # Construire le chemin du plugin pour obtenir ses paramètres
                plugins_base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'plugins')
                plugin_dir = os.path.join(plugins_base_dir, self.plugin_name)

                # Charger les paramètres du plugin depuis settings.yml
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

                file_content = FileContentHandler.process_file_content(plugin_settings, self.plugin_config, plugin_dir)
                # Intégrer le contenu des fichiers dans la configuration
                plugin_config_with_files = self.plugin_config.copy()

                for param_name, content in file_content.items():
                    plugin_config_with_files[param_name] = content
                    logger.info(f"Contenu du fichier intégré dans la configuration sous {param_name}")

                # Créer le fichier de configuration localement
                local_plugin_config = f"/tmp/{TEMP_FILE_PREFIX}plugin_config_{int(time.time())}.json"
                try:
                    with open(local_plugin_config, 'w') as f:
                        json.dump(plugin_config_with_files, f, indent=2)
                    
                    # Envoyer la configuration
                    remote_plugin_config = os.path.join(temp_dir, 'config.json')
                    await loop.run_in_executor(
                        None,
                        lambda: sftp.put(local_plugin_config, remote_plugin_config)
                    )
                finally:
                    # Nettoyer le fichier temporaire local
                    if os.path.exists(local_plugin_config):
                        os.remove(local_plugin_config)


                
                # Copier le script wrapper
                wrapper_path = os.path.join(os.path.dirname(__file__), 'ssh_wrapper.py')
                remote_wrapper = os.path.join(temp_dir, 'ssh_wrapper.py')
                await loop.run_in_executor(
                    None,
                    lambda: sftp.put(wrapper_path, remote_wrapper)
                )
                
                # Créer la configuration du wrapper
                wrapper_config = {
                    'plugin_path': os.path.join(temp_dir, 'exec.py'),
                    'plugin_config': plugin_config_with_files,
                    'needs_sudo': plugin_settings.get('needs_sudo', False),
                }
                
                # Créer le fichier de configuration localement
                local_wrapper_config = f"/tmp/{TEMP_FILE_PREFIX}wrapper_config_{int(time.time())}.json"
                try:
                    with open(local_wrapper_config, 'w') as f:
                        json.dump(wrapper_config, f, indent=2)
                    
                    # Envoyer la configuration
                    remote_wrapper_config = os.path.join(temp_dir, 'wrapper_config.json')
                    await loop.run_in_executor(
                        None,
                        lambda: sftp.put(local_wrapper_config, remote_wrapper_config)
                    )
                finally:
                    # Nettoyer le fichier temporaire local
                    if os.path.exists(local_wrapper_config):
                        os.remove(local_wrapper_config)
                

                # Rendre le script wrapper exécutable
                await loop.run_in_executor(
                    None,
                    lambda: ssh.exec_command(f"chmod +x {remote_wrapper}")
                )
                
                cmd = f"python3 {remote_wrapper} {remote_wrapper_config}"
                stdin, stdout, stderr = await loop.run_in_executor(
                    None,
                    lambda: ssh.exec_command(cmd, timeout=300, get_pty=True)  # Ajout de get_pty=True
                )
                # Récupérer les sorties en temps réel
                collected_output = []
                collected_errors = []
                
                # Fonction pour lire un flux de manière asynchrone
                async def read_stream(stream, is_stderr=False):
                    app = self.app if hasattr(self, 'app') else None
                    target_ip = host  # Utiliser l'adresse IP de l'hôte
                    
                    while True:
                        line = await loop.run_in_executor(None, stream.readline)
                        if not line:
                            break
                            
                        if not isinstance(line, bytes):
                            line_text=line.strip()
                        else:
                            line_text = line.decode('utf-8', errors='replace').strip()
                        if not line_text:
                            continue
                            
                        # Collecter les sorties
                        if is_stderr:
                            collected_errors.append(line_text)
                        else:
                            collected_output.append(line_text)
                        
                        # Si nous avons accès à l'application et aux utilitaires de log, traiter la ligne
                        try:
                            if app and hasattr(LoggerUtils, 'process_output_line'):
                                # Envoyer à l'app pour affichage en temps réel
                                await LoggerUtils.process_output_line(
                                    app, 
                                    line_text, 
                                    plugin_widget,  # Utiliser le plugin_widget passé en paramètre
                                    target_ip=target_ip
                                )
                        except Exception as e:
                            logger.error(f"Erreur lors du traitement en temps réel: {e}")
                
                # Créer des tâches pour lire les flux stdout et stderr
                stdout_task = asyncio.create_task(read_stream(stdout))
                stderr_task = asyncio.create_task(read_stream(stderr, True))
                
                # Attendre que les tâches soient terminées
                await asyncio.gather(stdout_task, stderr_task)
                
                # Attendre la fin du processus pour obtenir le code de retour
                exit_status = await loop.run_in_executor(
                    None,
                    lambda: stderr.channel.recv_exit_status()
                )
                
                if exit_status != 0:
                    error_message = "\n".join(collected_errors) if collected_errors else "Erreur inconnue"
                    return False, f"Erreur lors de l'exécution: {error_message}"

                output_text = "\n".join(collected_output)
                return True, output_text
                
                
            finally:
                # Fermer les connexions de manière asynchrone
                try:
                    if 'sftp' in locals() and sftp:
                        await loop.run_in_executor(None, lambda: sftp.close())
                    if 'ssh' in locals() and ssh:
                        await loop.run_in_executor(None, lambda: ssh.close())
                except Exception as e:
                    logger.warning(f"Erreur lors de la fermeture des connexions: {e}")
                
        except Exception as e:
            return False, f"Erreur lors de l'exécution sur {host}: {str(e)}"

    async def execute_plugin(self, plugin_widget, folder_name: str, config: dict) -> Tuple[bool, str]:
        """Exécute un plugin sur les machines distantes via SSH"""
        try:
            # Récupérer la configuration SSH
            ssh_config = SSHConfigLoader.get_instance().get_authentication_config()
            plugin_config = config.get('config', {})
            
            # Récupérer les adresses IP cibles
            target_ips = []
            for key in ['ssh_ips', 'target_ip']:
                if key in plugin_config:
                    value = plugin_config[key]
                    if isinstance(value, str):
                        target_ips.extend(ip.strip() for ip in value.split(',') if ip.strip())
                    elif isinstance(value, list):
                        target_ips.extend(ip.strip() for ip in value if ip.strip())
            
            if not target_ips:
                target_ips = get_target_ips(config)
            
            # Filtrer les IPs vides ou None
            target_ips = [ip for ip in target_ips if ip and ip.strip()]
            
            if not target_ips:
                logger.error(ERROR_MESSAGES['no_target_ips'])
                return False, ERROR_MESSAGES['no_target_ips']
            
            logger.info(f"IPs cibles trouvées: {target_ips}")
            
            # Récupérer les paramètres SSH
            ssh_user = ssh_config.get('ssh_user', '')
            ssh_password = ssh_config.get('ssh_passwd', '')
            ssh_port = ssh_config.get('ssh_port', DEFAULT_SSH_PORT)
            
            # Vérifier les identifiants SSH
            if not ssh_user or not ssh_password:
                ssh_user = plugin_config.get('ssh_user', '')
                ssh_password = plugin_config.get('ssh_passwd', '')
                
                if not ssh_user or not ssh_password:
                    logger.error(ERROR_MESSAGES['no_ssh_creds'])
                    return False, ERROR_MESSAGES['no_ssh_creds']
                
                logger.info("Utilisation des identifiants SSH du plugin")
            
            logger.info(f"Utilisation des identifiants SSH: utilisateur={ssh_user}, port={ssh_port}")
            
            # Exécuter le plugin sur chaque machine
            results = []
            for ip in target_ips:
                # Créer une configuration SSH spécifique pour cette IP avec les bons identifiants
                host_ssh_config = {
                    'user': ssh_user,
                    'password': ssh_password,
                    'port': ssh_port
                }
                
                success, output = await self._execute_on_single_host(
                    ip, host_ssh_config
                )
                results.append((success, output))
            
            # Consolider les résultats
            all_success = all(success for success, _ in results)
            all_outputs = [output for _, output in results]
            
            if all_success:
                return True, "\n".join(all_outputs)
            else:
                error_msg = f"{ERROR_MESSAGES['execution_failed']}:\n" + "\n".join(all_outputs)
                return False, error_msg
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Erreur lors de l'exécution du plugin {folder_name}: {error_msg}")
            logger.error(traceback.format_exc())
            return False, error_msg