"""
Module pour l'exécution des plugins via SSH.
"""

import os
import json
import time
import asyncio
import ipaddress
import pexpect
import socket
from typing import List, Tuple, Dict, Any, Optional
from ruamel.yaml import YAML

from ..utils.logging import get_logger
from ..utils.messaging import Message, MessageType, parse_message
from ..ssh_manager.ssh_config_loader import SSHConfigLoader
from .logger_utils import LoggerUtils
from .file_content_handler import FileContentHandler
from .local_executor import LocalExecutor
from .root_credentials_manager import RootCredentialsManager

logger = get_logger('ssh_executor')

class SSHExecutor:
    """Classe pour l'exécution des plugins via SSH"""
    
    def __init__(self, ssh_config=None):
        """Initialise l'exécuteur SSH avec une configuration
        
        Args:
            ssh_config: Configuration SSH (optionnelle)
        """
        self.ssh_config = ssh_config or {}
        
    async def execute_plugin(self, folder_name: str, config: dict) -> Tuple[bool, str]:
        """Exécute un plugin via SSH
        
        Args:
            folder_name: Le nom du dossier du plugin
            config: La configuration du plugin
            
        Returns:
            Tuple contenant le succès (bool) et la sortie (str)
        """
        try:
            logger.info(f"Exécution SSH du plugin {folder_name}")
            
            # Récupérer les informations SSH
            ssh_ip = self.ssh_config.get('ip')
            ssh_user = self.ssh_config.get('user', 'root')
            ssh_password = self.ssh_config.get('password', '')
            ssh_port = self.ssh_config.get('port', 22)
            
            if not ssh_ip:
                return False, "Adresse IP SSH manquante"
            
            # Construire le chemin du plugin sur la machine distante
            remote_plugin_dir = f"/tmp/pcutils_plugins/{folder_name}"
            
            # Préparer la commande SSH
            ssh_cmd = f"ssh -p {ssh_port} {ssh_user}@{ssh_ip}"
            
            # Construire le chemin du plugin
            plugin_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "plugins", folder_name)
            
            # Vérifier si c'est un plugin bash
            if os.path.exists(os.path.join(plugin_dir, "main.sh")):
                logger.info(f"Détecté comme plugin bash")
                is_bash_plugin = True
                exec_path = "main.sh"
            else:
                # Sinon c'est un plugin Python
                exec_path = "exec.py"
                logger.info(f"Détecté comme plugin Python")
                is_bash_plugin = False
            
            # Préparer la commande d'exécution
            if is_bash_plugin:
                remote_cmd = f"mkdir -p {remote_plugin_dir} && cd {remote_plugin_dir} && bash {exec_path} {config.get('name', 'test')} {config.get('intensity', 'light')}"
            else:
                # Sérialiser la configuration
                config_json = json.dumps(config).replace('"', '\\"')
                remote_cmd = f"mkdir -p {remote_plugin_dir} && cd {remote_plugin_dir} && python3 {exec_path} \"{config_json}\""
            
            # Combiner les commandes
            full_cmd = f"{ssh_cmd} \"{remote_cmd}\""
            
            # Exécuter la commande
            logger.info(f"Exécution de la commande SSH: {full_cmd}")
            process = await asyncio.create_subprocess_shell(
                full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Récupérer la sortie
            stdout, stderr = await process.communicate()
            
            # Vérifier le code de retour
            if process.returncode != 0:
                logger.error(f"Erreur lors de l'exécution SSH du plugin {folder_name}: {stderr.decode()}")
                return False, stderr.decode()
            
            # Succès
            logger.info(f"Plugin {folder_name} exécuté avec succès via SSH")
            return True, stdout.decode()
            
        except Exception as e:
            logger.error(f"Erreur lors de l'exécution SSH du plugin {folder_name}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False, str(e)
    
    @staticmethod
    def get_config() -> Dict[str, Any]:
        """Récupère la configuration SSH"""
        return SSHConfigLoader.get_instance().get_config()
    
    @staticmethod
    async def resolve_ips(app, ssh_ips, ssh_exception_ips):
        """Résout les IP avec wildcards et filtre les exclusions"""
        valid_ips = []
        excluded_ips = []
        
        # Traitement des IPs à exclure
        exclusions = ssh_exception_ips.split(',') if ssh_exception_ips else []
        exclusions = [e.strip() for e in exclusions if e.strip()]
        
        # Traitement des IPs candidates
        ip_candidates = ssh_ips.split(',') if ssh_ips else []
        ip_candidates = [ip.strip() for ip in ip_candidates if ip.strip()]
        
        for ip_pattern in ip_candidates:
            # Si c'est un pattern avec wildcard
            if '*' in ip_pattern:
                base_ip = ip_pattern.replace('*', '')
                # Pour chaque possibilité (1-254)
                for i in range(1, 255):
                    ip = base_ip + str(i)
                    # Vérifier si cette IP est exclue
                    if any(ip.startswith(excl.replace('*', '')) for excl in exclusions if '*' in excl) or ip in exclusions:
                        excluded_ips.append(ip)
                        continue
                    # Tester la connectivité
                    if await SSHExecutor.test_connectivity(app, ip):
                        valid_ips.append(ip)
            else:
                # IP précise
                if ip_pattern in exclusions:
                    excluded_ips.append(ip_pattern)
                    continue
                # Tester la connectivité
                if await SSHExecutor.test_connectivity(app, ip_pattern):
                    valid_ips.append(ip_pattern)
        
        return valid_ips, excluded_ips
    
    @staticmethod
    async def test_connectivity(app, ip_address):
        """Teste si une IP répond au ping avec des diagnostics améliorés"""
        try:
            # Utiliser un timeout plus long et plusieurs tentatives pour améliorer la fiabilité
            debug_msg = Message(
                type=MessageType.DEBUG,
                content=f"Test de connectivité pour {ip_address}..."
            )
            await LoggerUtils.display_message(app, debug_msg)
            logger.debug(f"Début du test de connectivité pour {ip_address}")
            
            # Utiliser plus de paquets et un timeout plus long pour améliorer la fiabilité
            process = await asyncio.create_subprocess_exec(
                "ping", "-c", "3", "-W", "3", ip_address,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            exit_code = process.returncode
            stdout_str = stdout.decode('utf-8', errors='replace') if stdout else ''
            stderr_str = stderr.decode('utf-8', errors='replace') if stderr else ''
            
            # Journaliser le résultat pour le diagnostic
            if exit_code == 0:
                # Extraire les statistiques pour un meilleur diagnostic
                stats_line = [line for line in stdout_str.split('\n') if 'packets transmitted' in line]
                stats = stats_line[0] if stats_line else 'Statistiques non disponibles'
                logger.debug(f"Ping réussi pour {ip_address}: {stats}")
                debug_msg = Message(
                    type=MessageType.DEBUG,
                    content=f"Connectivité OK pour {ip_address}: {stats}"
                )
                await LoggerUtils.display_message(app, debug_msg)
                
                # Tester également la connectivité SSH sur le port 22
                try:
                    # Obtenir le port SSH depuis la configuration
                    ssh_config_loader = SSHConfigLoader.get_instance()
                    auth_config = ssh_config_loader.get_authentication_config()
                    ssh_port = auth_config.get('ssh_port', '22')
                    
                    logger.debug(f"Test de la connectivité SSH (port {ssh_port}) pour {ip_address}")
                    ssh_test_process = await asyncio.create_subprocess_exec(
                        "nc", "-z", "-w", "3", ip_address, ssh_port,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    ssh_exit_code = await ssh_test_process.wait()
                    
                    if ssh_exit_code == 0:
                        logger.debug(f"Port SSH ({ssh_port}) ouvert sur {ip_address}")
                        debug_msg = Message(
                            type=MessageType.DEBUG,
                            content=f"Port SSH ({ssh_port}) ouvert sur {ip_address}"
                        )
                    else:
                        logger.debug(f"Port SSH ({ssh_port}) fermé sur {ip_address} malgré ping réussi")
                        debug_msg = Message(
                            type=MessageType.WARNING,
                            content=f"Port SSH ({ssh_port}) fermé sur {ip_address} malgré ping réussi"
                        )
                    
                    await LoggerUtils.display_message(app, debug_msg)
                    return ssh_exit_code == 0  # Retourner le résultat du test SSH plutôt que du ping
                except Exception as ssh_e:
                    logger.error(f"Erreur lors du test SSH pour {ip_address}: {str(ssh_e)}")
                    # Continuer avec le résultat du ping si le test SSH échoue
                    return True
            else:
                logger.debug(f"Ping échoué pour {ip_address} (code: {exit_code})")
                debug_msg = Message(
                    type=MessageType.DEBUG,
                    content=f"Échec de connectivité pour {ip_address} (code: {exit_code})"
                )
                await LoggerUtils.display_message(app, debug_msg)
                
                if stdout_str:
                    logger.debug(f"Sortie ping: {stdout_str}")
                    debug_msg = Message(
                        type=MessageType.DEBUG,
                        content=f"Sortie ping: {stdout_str[:150]}..." if len(stdout_str) > 150 else f"Sortie ping: {stdout_str}"
                    )
                    await LoggerUtils.display_message(app, debug_msg)
                    
                if stderr_str:
                    logger.debug(f"Erreur ping: {stderr_str}")
                    debug_msg = Message(
                        type=MessageType.DEBUG,
                        content=f"Erreur ping: {stderr_str[:150]}..." if len(stderr_str) > 150 else f"Erreur ping: {stderr_str}"
                    )
                    await LoggerUtils.display_message(app, debug_msg)
                
                return False
        except Exception as e:
            logger.error(f"Erreur lors du test de connectivité pour {ip_address}: {str(e)}")
            debug_msg = Message(
                type=MessageType.ERROR,
                content=f"Erreur lors du test de connectivité pour {ip_address}: {str(e)}"
            )
            await LoggerUtils.display_message(app, debug_msg)
            return False
    
    @staticmethod
    async def execute_ssh(app, ip_address, username, password, plugin_dir, plugin_id, plugin_config, plugin_widget=None):
        """Exécute un plugin via SSH sur une machine distante"""
        try:
            # Vérifier si on doit utiliser l'exécution locale
            if SSHConfigLoader.get_instance().should_use_local_execution(ip_address):
                info_msg = Message(
                    type=MessageType.INFO,
                    content=f"Utilisation de l'exécution locale pour {ip_address}"
                )
                await LoggerUtils.display_message(app, info_msg)
                
                from .local_executor import LocalExecutor
                # Créer une file d'attente pour les résultats
                result_queue = asyncio.Queue()
                # Exécuter le plugin localement
                await LocalExecutor.run_local_plugin(
                    app, plugin_id, app.plugins[plugin_id], 
                    plugin_config.get('name', plugin_id), plugin_config, 0, 1, result_queue
                )
                # Récupérer le résultat
                success, message = await result_queue.get()
                return success, message
            
            # Obtenir les paramètres de configuration
            ssh_config_loader = SSHConfigLoader.get_instance()
            connection_config = ssh_config_loader.get_connection_config()
            auth_config = ssh_config_loader.get_authentication_config()
            
            # Récupérer les timeouts depuis la configuration
            connect_timeout = connection_config.get('connect_timeout', 10)
            transfer_timeout = connection_config.get('transfer_timeout', 60)
            command_timeout = connection_config.get('command_timeout', 120)
            
            # Informer de la connexion SSH
            info_msg = Message(
                type=MessageType.INFO,
                content=f"Connexion SSH à {ip_address}..."
            )
            await LoggerUtils.display_message(app, info_msg)
            
            # Journaliser les détails de la connexion pour le diagnostic
            debug_msg = Message(
                type=MessageType.DEBUG,
                content=f"Tentative SSH vers {username}@{ip_address} (timeout: {connect_timeout}s)"
            )
            await LoggerUtils.display_message(app, debug_msg)
            logger.debug(f"Tentative de connexion SSH: {username}@{ip_address}")
            
            # Obtenir le port SSH depuis la configuration
            ssh_port = auth_config.get('ssh_port', '22')
            logger.debug(f"Utilisation du port SSH: {ssh_port}")
            
            # Créer le processus SSH avec pexpect avec des options supplémentaires pour la stabilité
            ssh_command = f"ssh -p {ssh_port} -o ConnectTimeout={connect_timeout} -o ServerAliveInterval=5 -o ServerAliveCountMax=3 {username}@{ip_address}"
            logger.debug(f"Commande SSH complète: {ssh_command}")
            ssh_process = pexpect.spawn(ssh_command, encoding='utf-8')
            
            # Activer la journalisation de pexpect pour le diagnostic
            class SSHLogger:
                def write(self, data):
                    # Nettoyer les données pour une meilleure lisibilité
                    clean_data = data.strip() if isinstance(data, str) else str(data)
                    if clean_data:  # Ne pas logger les lignes vides
                        logger.debug(f"SSH output: {clean_data}")
                def flush(self):
                    pass
            
            ssh_process.logfile_read = SSHLogger()
            
            # Gérer l'authentification
            debug_msg = Message(
                type=MessageType.DEBUG,
                content=f"Attente du prompt de mot de passe pour {ip_address}..."
            )
            await LoggerUtils.display_message(app, debug_msg)
            
            i = ssh_process.expect(['password:', 'continue connecting', pexpect.TIMEOUT, pexpect.EOF], timeout=connect_timeout)
            if i == 0:
                debug_msg = Message(
                    type=MessageType.DEBUG,
                    content=f"Prompt de mot de passe détecté pour {ip_address}, envoi du mot de passe"
                )
                await LoggerUtils.display_message(app, debug_msg)
                ssh_process.sendline(password)
            elif i == 1:
                # Auto-accepter la clé d'hôte si configuré
                debug_msg = Message(
                    type=MessageType.DEBUG,
                    content=f"Nouvelle clé d'hôte détectée pour {ip_address}"
                )
                await LoggerUtils.display_message(app, debug_msg)
                
                if auth_config.get('auto_add_keys', True):
                    debug_msg = Message(
                        type=MessageType.DEBUG,
                        content=f"Acceptation automatique de la clé pour {ip_address}"
                    )
                    await LoggerUtils.display_message(app, debug_msg)
                    ssh_process.sendline('yes')
                    
                    j = ssh_process.expect(['password:', pexpect.TIMEOUT, pexpect.EOF], timeout=connect_timeout)
                    if j == 0:
                        debug_msg = Message(
                            type=MessageType.DEBUG,
                            content=f"Prompt de mot de passe après acceptation de la clé pour {ip_address}"
                        )
                        await LoggerUtils.display_message(app, debug_msg)
                        ssh_process.sendline(password)
                    else:
                        error_msg = Message(
                            type=MessageType.ERROR,
                            content=f"Pas de prompt de mot de passe après acceptation de la clé pour {ip_address}"
                        )
                        await LoggerUtils.display_message(app, error_msg)
                        return False, f"Erreur après acceptation de la clé pour {ip_address}"
                else:
                    return False, f"Nouvelle clé d'hôte détectée pour {ip_address}, mais l'acceptation automatique est désactivée"
            elif i == 2:  # TIMEOUT
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Timeout lors de la connexion à {ip_address} (après {connect_timeout}s)"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Timeout lors de la connexion à {ip_address} (après {connect_timeout}s)"
            else:  # EOF
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Connexion fermée prématurément pour {ip_address}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Connexion fermée prématurément pour {ip_address}"
            
            # Vérifier l'authentification
            debug_msg = Message(
                type=MessageType.DEBUG,
                content=f"Vérification de l'authentification pour {ip_address}..."
            )
            await LoggerUtils.display_message(app, debug_msg)
            
            i = ssh_process.expect(['$', '#', 'Permission denied', 'Authentication failed', pexpect.TIMEOUT, pexpect.EOF], timeout=connect_timeout)
            if i == 0 or i == 1:  # Prompt shell détecté
                success_msg = Message(
                    type=MessageType.SUCCESS,
                    content=f"Authentification réussie sur {ip_address}"
                )
                await LoggerUtils.display_message(app, success_msg)
            elif i == 2 or i == 3:  # Erreur d'authentification explicite
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Authentification refusée pour {username}@{ip_address} - mot de passe incorrect"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Authentification refusée pour {username}@{ip_address}"
            elif i == 4:  # TIMEOUT
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Timeout lors de l'authentification sur {ip_address}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Timeout lors de l'authentification sur {ip_address}"
            else:  # EOF
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Connexion fermée pendant l'authentification sur {ip_address}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Connexion fermée pendant l'authentification sur {ip_address}"
            
            # Connexion établie
            success_msg = Message(
                type=MessageType.SUCCESS,
                content=f"Connexion établie avec {ip_address}"
            )
            await LoggerUtils.display_message(app, success_msg)
            
            # Obtenir les paramètres d'exécution
            execution_config = ssh_config_loader.get_execution_config()
            remote_temp_dir = execution_config.get('remote_temp_dir', '/tmp/pcutils')
            cleanup_temp_files = execution_config.get('cleanup_temp_files', True)
            
            # Créer un répertoire temporaire
            temp_dir = f"{remote_temp_dir}_{plugin_id}_{int(time.time())}"
            debug_msg = Message(
                type=MessageType.DEBUG,
                content=f"Création du répertoire temporaire: {temp_dir} sur {ip_address}"
            )
            await LoggerUtils.display_message(app, debug_msg)
            
            ssh_process.sendline(f"mkdir -p {temp_dir}")
            i = ssh_process.expect(['$', '#', pexpect.TIMEOUT, pexpect.EOF], timeout=connect_timeout)
            if i >= 2:
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Impossible de créer le répertoire temporaire sur {ip_address}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Impossible de créer le répertoire temporaire sur {ip_address}"
            
            # Vérifier que le répertoire a bien été créé
            ssh_process.sendline(f"ls -la {temp_dir}")
            i = ssh_process.expect(['$', '#', 'No such file', pexpect.TIMEOUT, pexpect.EOF], timeout=connect_timeout)
            if i == 2:
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Le répertoire temporaire n'a pas été créé sur {ip_address}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Le répertoire temporaire n'a pas été créé sur {ip_address}"
            elif i >= 3:
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Erreur lors de la vérification du répertoire temporaire sur {ip_address}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Erreur lors de la vérification du répertoire temporaire sur {ip_address}"
            
            # Transférer les fichiers (utiliser un autre processus pexpect pour scp)
            info_msg = Message(
                type=MessageType.INFO,
                content=f"Transfert des fichiers vers {ip_address}..."
            )
            await LoggerUtils.display_message(app, info_msg)
            
            # Vérifier que la connexion SSH est toujours active
            if ssh_process.isalive():
                logger.debug(f"Connexion SSH active avant transfert de fichiers vers {ip_address}")
            else:
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"La connexion SSH a été perdue avant le transfert de fichiers vers {ip_address}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"La connexion SSH a été perdue avant le transfert de fichiers vers {ip_address}"
            
            # Vérifier que le répertoire source existe
            debug_msg = Message(
                type=MessageType.DEBUG,
                content=f"Vérification du répertoire source: {plugin_dir}"
            )
            await LoggerUtils.display_message(app, debug_msg)
            
            if not os.path.exists(plugin_dir):
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Répertoire source introuvable: {plugin_dir}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Répertoire source introuvable: {plugin_dir}"
            
            # Journaliser le contenu du répertoire source pour le diagnostic
            files = os.listdir(plugin_dir)
            debug_msg = Message(
                type=MessageType.DEBUG,
                content=f"Fichiers à transférer: {', '.join(files)}"
            )
            await LoggerUtils.display_message(app, debug_msg)
            
            debug_msg = Message(
                type=MessageType.DEBUG,
                content=f"Préparation du transfert SCP vers {ip_address}"
            )
            await LoggerUtils.display_message(app, debug_msg)
            
            # Obtenir le port SSH depuis la configuration
            ssh_port = auth_config.get('ssh_port', '22')
            
            # Activer la journalisation pour SCP avec des options supplémentaires pour la stabilité
            # Vérifier que le répertoire source contient des fichiers
            if not os.listdir(plugin_dir):
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Répertoire source vide: {plugin_dir}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Répertoire source vide: {plugin_dir}"
                
            # Utiliser le répertoire lui-même plutôt que le contenu avec * pour éviter les problèmes de glob
            scp_command = f"scp -P {ssh_port} -o ConnectTimeout={connect_timeout} -o ServerAliveInterval=5 -o ServerAliveCountMax=3 -r {plugin_dir} {username}@{ip_address}:{temp_dir}/"
            logger.debug(f"Commande SCP complète: {scp_command}")
            scp_process = pexpect.spawn(scp_command, encoding='utf-8')
            class SCPLogger:
                def write(self, data):
                    # Nettoyer les données pour une meilleure lisibilité
                    clean_data = data.strip() if isinstance(data, str) else str(data)
                    if clean_data:  # Ne pas logger les lignes vides
                        logger.debug(f"SCP output: {clean_data}")
                def flush(self):
                    pass
            
            scp_process.logfile_read = SCPLogger()
            
            i = scp_process.expect(['password:', 'No such file', pexpect.TIMEOUT, pexpect.EOF], timeout=connect_timeout)
            if i == 0:
                debug_msg = Message(
                    type=MessageType.DEBUG,
                    content=f"Prompt de mot de passe SCP détecté pour {ip_address}"
                )
                await LoggerUtils.display_message(app, debug_msg)
                scp_process.sendline(password)
            elif i == 1:
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Fichier ou répertoire introuvable lors du transfert vers {ip_address}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Fichier ou répertoire introuvable lors du transfert vers {ip_address}"
            elif i == 2:
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Timeout lors du transfert SCP vers {ip_address}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Timeout lors du transfert SCP vers {ip_address}"
            
            # Attendre la fin du transfert
            debug_msg = Message(
                type=MessageType.DEBUG,
                content=f"Attente de la fin du transfert SCP vers {ip_address} (timeout: {transfer_timeout}s)"
            )
            await LoggerUtils.display_message(app, debug_msg)
            
            i = scp_process.expect(['100%', 'Permission denied', 'No such file', pexpect.TIMEOUT, pexpect.EOF], timeout=transfer_timeout)
            if i == 0:
                debug_msg = Message(
                    type=MessageType.DEBUG,
                    content=f"Transfert SCP terminé à 100% vers {ip_address}"
                )
                await LoggerUtils.display_message(app, debug_msg)
            elif i == 1:
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Permission refusée lors du transfert SCP vers {ip_address}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Permission refusée lors du transfert SCP vers {ip_address}"
            elif i == 2:
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Fichier ou répertoire introuvable lors du transfert SCP vers {ip_address}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Fichier ou répertoire introuvable lors du transfert SCP vers {ip_address}"
            elif i == 3:
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Timeout lors du transfert SCP vers {ip_address} (après {transfer_timeout}s)"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Timeout lors du transfert SCP vers {ip_address}"
            
            # Vérifier que les fichiers ont bien été transférés
            ssh_process.sendline(f"ls -la {temp_dir}")
            i = ssh_process.expect(['$', '#', pexpect.TIMEOUT, pexpect.EOF], timeout=connect_timeout)
            if i >= 2:
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Impossible de vérifier les fichiers transférés sur {ip_address}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Impossible de vérifier les fichiers transférés sur {ip_address}"
            
            success_msg = Message(
                type=MessageType.SUCCESS,
                content=f"Transfert terminé vers {ip_address}"
            )
            await LoggerUtils.display_message(app, success_msg)
            
            # Identifier le type de plugin
            is_bash_plugin = os.path.exists(os.path.join(plugin_dir, "main.sh"))
            
            # Vérifier que les fichiers nécessaires existent sur la machine locale
            if is_bash_plugin:
                bash_script = os.path.join(plugin_dir, "main.sh")
                if not os.path.exists(bash_script):
                    error_msg = Message(
                        type=MessageType.ERROR,
                        content=f"Script bash introuvable: {bash_script}"
                    )
                    await LoggerUtils.display_message(app, error_msg)
                    return False, f"Script bash introuvable: {bash_script}"
                
                debug_msg = Message(
                    type=MessageType.DEBUG,
                    content=f"Utilisation du script bash: {bash_script}"
                )
                await LoggerUtils.display_message(app, debug_msg)
            else:
                python_script = os.path.join(plugin_dir, "exec.py")
                if not os.path.exists(python_script):
                    error_msg = Message(
                        type=MessageType.ERROR,
                        content=f"Script Python introuvable: {python_script}"
                    )
                    await LoggerUtils.display_message(app, error_msg)
                    return False, f"Script Python introuvable: {python_script}"
                
                debug_msg = Message(
                    type=MessageType.DEBUG,
                    content=f"Utilisation du script Python: {python_script}"
                )
                await LoggerUtils.display_message(app, debug_msg)
            
            # Vérifier que les fichiers ont bien été transférés sur la machine distante
            if is_bash_plugin:
                ssh_process.sendline(f"ls -la {temp_dir}/main.sh")
            else:
                ssh_process.sendline(f"ls -la {temp_dir}/exec.py")
            
            i = ssh_process.expect(['$', '#', 'No such file', pexpect.TIMEOUT, pexpect.EOF], timeout=connect_timeout)
            if i == 2:
                script_type = "bash" if is_bash_plugin else "Python"
                error_msg = Message(MessageType.ERROR, f"Script {script_type} non transféré sur {ip_address}")
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Script {script_type} non transféré sur {ip_address}"
            elif i >= 3:
                error_msg = Message(MessageType.ERROR, f"Erreur lors de la vérification des fichiers sur {ip_address}")
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Erreur lors de la vérification des fichiers sur {ip_address}"
            
            # Vérifier dans les paramètres de plugin (settings.yml)
            settings_path = os.path.join(plugin_dir, "settings.yml")
            plugin_settings = {}
            if os.path.exists(settings_path):
                try:
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        plugin_settings = YAML().load(f)
                        logger.info(f"Paramètres du plugin chargés depuis {settings_path}")
                except Exception as e:
                    logger.error(f"Erreur lors de la lecture des paramètres du plugin: {e}")
            
            # Traiter le contenu des fichiers de configuration
            file_content = FileContentHandler.process_file_content(plugin_settings, plugin_config, plugin_dir)
            
            # Intégrer le contenu des fichiers dans la configuration
            for param_name, content in file_content.items():
                plugin_config[param_name] = content
                logger.info(f"Contenu du fichier intégré dans la configuration sous {param_name}")
            
            # Afficher la structure de la configuration pour le débogage
            logger.debug(f"Structure de la configuration après ajout des fichiers: {list(plugin_config.keys())}")
            
            # Vérifier si le plugin nécessite des droits root
            needs_root = False
            if plugin_settings and isinstance(plugin_settings, dict):
                needs_root = plugin_settings.get('ssh_root', False)
                logger.info(f"Plugin {plugin_id} nécessite des droits root: {needs_root}")
            
            # Préparer la commande d'exécution
            if is_bash_plugin:
                base_cmd = f"cd {temp_dir} && bash main.sh '{plugin_config.get('name', 'test')}' '{plugin_config.get('intensity', 'light')}'"
            else:
                # Pour un plugin Python, convertir la config en JSON
                json_config = json.dumps(plugin_config).replace("'", "\\'") 
                # Obtenir le nom du dossier du plugin pour accéder au fichier exec.py
                plugin_folder = os.path.basename(plugin_dir)
                # Vérifier si nous devons utiliser le sous-répertoire du plugin ou le répertoire temporaire directement
                base_cmd = f"cd {temp_dir} && python3 {plugin_folder}/exec.py '{json_config}'"
            
            # Obtenir le gestionnaire d'identifiants root
            root_credentials_manager = RootCredentialsManager.get_instance()
            running_as_root = root_credentials_manager.is_running_as_root()
            
            # Déterminer comment exécuter la commande en fonction des besoins et de l'utilisateur actuel
            cmd = base_cmd
            
            if needs_root and not running_as_root:
                # Cas 1: Le plugin nécessite des droits root et nous ne sommes pas root
                # Utiliser le gestionnaire d'identifiants root pour récupérer les identifiants
                root_credentials = root_credentials_manager.prepare_ssh_root_credentials(ip_address, plugin_config)
                
                # Récupérer l'utilisateur root
                ssh_root_user = root_credentials.get('user', 'root')
                
                # Utiliser sudo pour exécuter la commande avec les droits root
                cmd = f"sudo -S {base_cmd}"
                debug_msg = Message(
                    type=MessageType.DEBUG,
                    content=f"Exécution en tant que root avec l'utilisateur {ssh_root_user}"
                )
                await LoggerUtils.display_message(app, debug_msg)
                
            elif not needs_root and running_as_root:
                # Cas 2: Le plugin ne nécessite pas de droits root mais nous sommes déjà root
                # Récupérer l'utilisateur original
                sudo_user = root_credentials_manager.get_sudo_user()
                
                if sudo_user:
                    # Utiliser su pour exécuter la commande en tant qu'utilisateur normal
                    cmd = f"su {sudo_user} -c '{base_cmd}'"
                    debug_msg = Message(
                        type=MessageType.DEBUG,
                        content=f"Exécution en tant qu'utilisateur {sudo_user} (déjà root)"
                    )
                    await LoggerUtils.display_message(app, debug_msg)
            
            elif needs_root and running_as_root:
                # Cas 3: Le plugin nécessite des droits root et nous sommes déjà root
                debug_msg = Message(
                    type=MessageType.DEBUG,
                    content=f"Exécution avec des droits root (déjà root)"
                )
                await LoggerUtils.display_message(app, debug_msg)
                # Pas besoin de modifier la commande, nous sommes déjà root
            
            debug_msg = Message(
                type=MessageType.DEBUG,
                content=f"Commande d'exécution sur {ip_address}: {cmd}"
            )
            await LoggerUtils.display_message(app, debug_msg)
            
            info_msg = Message(
                type=MessageType.INFO,
                content=f"Exécution du plugin sur {ip_address}..."
            )
            await LoggerUtils.display_message(app, info_msg)
            
            # Exécuter la commande
            ssh_process.sendline(cmd)
            
            # Gérer l'authentification si nécessaire
            running_as_root = root_credentials_manager.is_running_as_root()
            
            # Cas 1: Nous ne sommes pas root mais le plugin nécessite des droits root
            if needs_root and not running_as_root:
                i = ssh_process.expect(['[sudo] password', pexpect.TIMEOUT, pexpect.EOF], timeout=5)
                if i == 0:
                    # Récupérer le mot de passe depuis le gestionnaire d'identifiants root
                    root_credentials = root_credentials_manager.get_ssh_root_credentials(ip_address)
                    
                    if root_credentials and root_credentials.get('password'):
                        sudo_passwd = root_credentials.get('password')
                        ssh_process.sendline(sudo_passwd)
                        debug_msg = Message(
                            type=MessageType.DEBUG,
                            content=f"Mot de passe sudo envoyé pour {ip_address}"
                        )
                        await LoggerUtils.display_message(app, debug_msg)
                    else:
                        logger.warning(f"Aucun mot de passe sudo disponible pour {ip_address}, l'exécution pourrait échouer")
                        warning_msg = Message(
                            type=MessageType.WARNING,
                            content=f"Aucun mot de passe sudo disponible pour {ip_address}"
                        )
                        await LoggerUtils.display_message(app, warning_msg)
            
            # Cas 2: Nous sommes root mais le plugin ne nécessite pas de droits root
            # Dans ce cas, su ne demande pas de mot de passe car nous sommes déjà root
            
            # Vérifier les erreurs immédiates
            if is_bash_plugin:
                i = ssh_process.expect(['bash: command not found', 'No such file', 'Permission denied', '\n', pexpect.TIMEOUT, pexpect.EOF], timeout=5)
                if i == 0:
                    error_msg = Message(
                        type=MessageType.ERROR,
                        content=f"Bash n'est pas installé sur {ip_address}"
                    )
                    await LoggerUtils.display_message(app, error_msg)
                    return False, f"Bash n'est pas installé sur {ip_address}"
            else:
                i = ssh_process.expect(['python3: command not found', 'No such file', 'Permission denied', '\n', pexpect.TIMEOUT, pexpect.EOF], timeout=5)
                if i == 0:
                    error_msg = Message(
                        type=MessageType.ERROR,
                        content=f"Python3 n'est pas installé sur {ip_address}"
                    )
                    await LoggerUtils.display_message(app, error_msg)
                    return False, f"Python3 n'est pas installé sur {ip_address}"
            
            if i == 1:
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Fichier introuvable lors de l'exécution sur {ip_address}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Fichier introuvable lors de l'exécution sur {ip_address}"
            elif i == 2:
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Permission refusée lors de l'exécution sur {ip_address}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, f"Permission refusée lors de l'exécution sur {ip_address}"
            
            # Attendre et traiter la sortie ligne par ligne
            debug_msg = Message(
                type=MessageType.DEBUG,
                content=f"Lecture de la sortie d'exécution sur {ip_address}..."
            )
            await LoggerUtils.display_message(app, debug_msg)
            
            output = ""
            error_detected = False
            execution_timeout = command_timeout
            start_time = time.time()
            
            while True:
                try:
                    # Vérifier si on a dépassé le timeout global
                    elapsed_time = time.time() - start_time
                    if elapsed_time > execution_timeout:
                        error_msg = Message(
                            type=MessageType.ERROR,
                            content=f"Timeout global d'exécution sur {ip_address} après {int(elapsed_time)}s"
                        )
                        await LoggerUtils.display_message(app, error_msg)
                        error_detected = True
                        break
                    
                    # Attendre la prochaine ligne avec un timeout court
                    i = ssh_process.expect(['\n', 'Traceback', 'Error:', 'Exception', pexpect.TIMEOUT, pexpect.EOF], timeout=1)
                    
                    if i == 0:  # Nouvelle ligne
                        line = ssh_process.before
                        if line:
                            # Traiter la ligne avec préfixe IP
                            await SSHExecutor.process_ssh_output(app, line, ip_address, plugin_widget)
                            output += line + "\n"
                            
                            # Détecter les erreurs dans la sortie
                            if "error" in line.lower() or "exception" in line.lower() or "traceback" in line.lower():
                                debug_msg = Message(
                                    type=MessageType.DEBUG,
                                    content=f"Erreur détectée dans la sortie: {line}"
                                )
                                await LoggerUtils.display_message(app, debug_msg)
                    
                    elif i in [1, 2, 3]:  # Erreur Python détectée
                        error_type = "Traceback" if i == 1 else "Error" if i == 2 else "Exception"
                        error_msg = Message(
                            type=MessageType.ERROR,
                            content=f"{error_type} détecté lors de l'exécution sur {ip_address}"
                        )
                        await LoggerUtils.display_message(app, error_msg)
                        error_detected = True
                        
                        # Continuer à lire pour capturer le message d'erreur complet
                        error_output = ""
                        for _ in range(10):  # Lire jusqu'à 10 lignes supplémentaires pour capturer l'erreur
                            j = ssh_process.expect(['\n', pexpect.TIMEOUT, pexpect.EOF], timeout=0.5)
                            if j == 0:
                                error_line = ssh_process.before
                                if error_line:
                                    error_output += error_line + "\n"
                                    await SSHExecutor.process_ssh_output(app, error_line, ip_address, plugin_widget)
                            else:
                                break
                        
                        debug_msg = Message(
                            type=MessageType.DEBUG,
                            content=f"Détails de l'erreur: {error_output}"
                        )
                        await LoggerUtils.display_message(app, debug_msg)
                    
                    elif i == 4:  # Timeout court (continuer à attendre)
                        continue
                    
                    elif i == 5:  # EOF (fin de la sortie)
                        debug_msg = Message(
                            type=MessageType.DEBUG,
                            content=f"Fin de la sortie d'exécution sur {ip_address}"
                        )
                        await LoggerUtils.display_message(app, debug_msg)
                        break
                    
                except Exception as e:
                    logger.error(f"Erreur de lecture SSH: {str(e)}")
                    error_msg = Message(
                        type=MessageType.ERROR,
                        content=f"Erreur de lecture SSH: {str(e)}"
                    )
                    await LoggerUtils.display_message(app, error_msg)
                    error_detected = True
                    break
            
            # Nettoyer les fichiers temporaires si configuré
            debug_msg = Message(
                type=MessageType.DEBUG,
                content=f"Nettoyage des fichiers temporaires sur {ip_address}"
            )
            await LoggerUtils.display_message(app, debug_msg)
            
            if cleanup_temp_files:
                ssh_process.sendline(f"rm -rf {temp_dir}")
                ssh_process.expect(['$', '#', pexpect.TIMEOUT, pexpect.EOF], timeout=connect_timeout)
            
            # Fermer la connexion SSH proprement
            ssh_process.sendline("exit")
            
            # Vérifier si l'exécution s'est bien passée
            success_indicators = ["Exécution terminée avec succès", "Progression : 100%", "[SUCCESS]", "completed successfully"]
            success = any(indicator in output for indicator in success_indicators) and not error_detected
            
            # Journaliser le résultat de l'exécution
            logger.debug(f"Résultat de l'exécution sur {ip_address}: {'Succès' if success else 'Échec'}")
            
            # Journaliser la sortie complète
            logger.debug(f"Sortie complète de l'exécution SSH sur {ip_address} ({len(output)} caractères)")
            
            # Journaliser la sortie complète si configuré ou en cas d'erreur
            if ssh_config_loader.get_logging_config().get('log_full_output', False) or not success:
                logger.debug(f"Sortie complète de l'exécution SSH sur {ip_address}:\n{output}")
            
            if success:
                success_msg = Message(
                    type=MessageType.SUCCESS,
                    content=f"Exécution SSH terminée avec succès sur {ip_address}"
                )
                await LoggerUtils.display_message(app, success_msg)
                return True, "Exécution SSH terminée avec succès"
            else:
                error_msg = Message(
                    type=MessageType.ERROR,
                    content=f"Erreur lors de l'exécution SSH sur {ip_address}"
                )
                await LoggerUtils.display_message(app, error_msg)
                return False, "Erreur lors de l'exécution SSH"
                
        except Exception as e:
            logger.error(f"Erreur SSH: {str(e)}")
            return False, f"Erreur SSH: {str(e)}"
    
    @staticmethod
    async def process_ssh_output(app, line, ip_address=None, plugin_widget=None):
        """Traite la sortie SSH pour la mise à jour de l'UI"""
        try:
            # Ignorer les lignes vides
            if not line or (isinstance(line, str) and line.isspace()):
                return

            # Ajouter l'adresse IP au début de la ligne si fournie
            log_line = line.strip() if line else ""
            if ip_address and log_line:
                # Si la ligne est au format standardisé, insérer l'IP après le préfixe
                if log_line.startswith("[LOG]") or log_line.startswith("[PROGRESS]"):
                    parts = log_line.split(" ", 2)
                    if len(parts) >= 3:
                        log_line = f"{parts[0]} [{ip_address}] {parts[1]} {parts[2]}"
                    else:
                        log_line = f"[{ip_address}] {log_line}"
                else:
                    log_line = f"[{ip_address}] {log_line}"
            
            # Traiter la ligne avec le système de gestion des messages
            if plugin_widget:
                await LoggerUtils.process_output_line(app, log_line, plugin_widget, 0, 1)
            else:
                # Si pas de widget fourni, juste afficher le message
                message_obj = parse_message(log_line)
                await LoggerUtils.display_message(app, message_obj)
                
        except Exception as e:
            # En cas d'erreur lors du traitement, logger l'erreur directement
            logger.error(f"Erreur lors du traitement de la sortie SSH: {str(e)}")
            error_msg = Message(
                type=MessageType.ERROR,
                content=f"Erreur de traitement SSH: {str(e)}"
            )
            await LoggerUtils.display_message(app, error_msg)
    
    @staticmethod
    async def run_ssh_plugin(app, plugin_id, plugin_widget, plugin_show_name, config, executed, total_plugins, result_queue):
        """Exécute un plugin en mode SSH sur toutes les machines accessibles"""
        try:
            # Extraire le nom du plugin pour les logs
            folder_name = plugin_widget.folder_name
            logger.info(f"Démarrage du plugin {folder_name} ({plugin_id}) en mode SSH")
            
            # Initialiser la barre de progression
            plugin_widget.set_status('running')
            plugin_widget.update_progress(0.0, "Démarrage...")
            
            # Récupérer les paramètres SSH
            ssh_ips = config.get("ssh_ips", "")
            ssh_user = config.get("ssh_user", "")
            ssh_passwd = config.get("ssh_passwd", "")
            ssh_exception_ips = config.get("ssh_exception_ips", "")
            ssh_sms_enabled = config.get("ssh_sms_enabled", False)
            ssh_sms = config.get("ssh_sms", "")
            
            info_msg = Message(
                type=MessageType.INFO,
                content=f"Mode SSH activé pour {plugin_show_name}"
            )
            await LoggerUtils.display_message(app, info_msg)
            
            # Construire le chemin du plugin
            plugin_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "plugins", folder_name)
            
            # Résoudre et filtrer les IPs
            plugin_widget.update_progress(0.1, "Recherche des machines accessibles...")
            valid_ips, excluded_ips = await SSHExecutor.resolve_ips(app, ssh_ips, ssh_exception_ips)
            
            if excluded_ips:
                info_msg = Message(
                    type=MessageType.INFO,
                    content=f"IPs exclues: {', '.join(excluded_ips)}"
                )
                await LoggerUtils.display_message(app, info_msg)
            
            if not valid_ips:
                error_msg = Message(
                    type=MessageType.ERROR,
                    content="Aucune machine accessible trouvée"
                )
                await LoggerUtils.display_message(app, error_msg)
                plugin_widget.set_status('error', "Aucune machine accessible")
                await result_queue.put((False, "Aucune machine accessible trouvée"))
                return
            
            info_msg = Message(
                type=MessageType.INFO,
                content=f"Machines accessibles: {', '.join(valid_ips)}"
            )
            await LoggerUtils.display_message(app, info_msg)
            
            # Obtenir la configuration d'exécution
            ssh_config_loader = SSHConfigLoader.get_instance()
            execution_config = ssh_config_loader.get_execution_config()
            parallel_execution = execution_config.get('parallel_execution', False)
            max_parallel = execution_config.get('max_parallel', 5)
            
            # Exécution sur chaque IP valide
            total_ips = len(valid_ips)
            success_count = 0
            
            # Fonction pour exécuter un plugin sur une IP
            async def execute_on_ip(ip, progress_start, progress_end):
                nonlocal success_count
                # Mettre à jour la progression
                plugin_widget.update_progress(progress_start, f"Connexion à {ip}...")
                
                # Préparer la configuration avec les données SSH pour ce plugin
                plugin_config = config.copy()
                
                # Récupérer les informations d'authentification root
                ssh_root_same = config.get("ssh_root_same", True)
                ssh_root_user = config.get("ssh_root_user", "root") if not ssh_root_same else ssh_user
                ssh_root_passwd = config.get("ssh_root_passwd", "") if not ssh_root_same else ssh_passwd
                
                plugin_config.update({
                    "ssh_mode": True,
                    "ssh_ips": ssh_ips,
                    "ssh_current_ip": ip,
                    "ssh_user": ssh_user,
                    "ssh_passwd": ssh_passwd,
                    "ssh_exception_ips": ssh_exception_ips,
                    "ssh_sms_enabled": ssh_sms_enabled,
                    "ssh_sms": ssh_sms if ssh_sms_enabled else "",
                    "ssh_root_same": ssh_root_same,
                    "ssh_root_user": ssh_root_user,
                    "ssh_root_passwd": ssh_root_passwd
                })
                
                # Exécuter sur cette IP
                success, message = await SSHExecutor.execute_ssh(
                    app, ip, ssh_user, ssh_passwd, plugin_dir, plugin_id, plugin_config, plugin_widget
                )
                
                # Mettre à jour la progression
                plugin_widget.update_progress(progress_end, f"Terminé sur {ip}")
                
                if success:
                    success_count += 1
                    await LoggerUtils.display_message(app, Message(
                        type=MessageType.SUCCESS,
                        content=f"Exécution réussie sur {ip}"
                    ))
                else:
                    await LoggerUtils.display_message(app, Message(
                        type=MessageType.ERROR,
                        content=f"Échec sur {ip}: {message}"
                    ))
                
                return success, message
            
            # Exécution parallèle ou séquentielle selon la configuration
            if parallel_execution and total_ips > 1:
                info_msg = Message(
                    type=MessageType.INFO,
                    content=f"Exécution parallèle sur {min(total_ips, max_parallel)} machines"
                )
                await LoggerUtils.display_message(app, info_msg)
                
                # Créer des groupes d'IPs pour limiter la parallélisation
                for i in range(0, total_ips, max_parallel):
                    batch = valid_ips[i:i+max_parallel]
                    batch_size = len(batch)
                    
                    # Créer les tâches pour ce groupe
                    tasks = []
                    for j, ip in enumerate(batch):
                        progress_start = 0.1 + (0.9 * (i + j) / total_ips)
                        progress_end = 0.1 + (0.9 * (i + j + 1) / total_ips)
                        tasks.append(execute_on_ip(ip, progress_start, progress_end))
                    
                    # Exécuter les tâches en parallèle
                    await asyncio.gather(*tasks)
            else:
                # Exécution séquentielle
                for idx, ip in enumerate(valid_ips):
                    progress_start = 0.1 + (0.9 * idx / total_ips)
                    progress_end = 0.1 + (0.9 * (idx + 1) / total_ips)
                    await execute_on_ip(ip, progress_start, progress_end)
            
            # Résultat final
            if success_count > 0:
                final_message = f"Exécution réussie sur {success_count}/{total_ips} machines"
                plugin_widget.set_status('success', final_message)
                await result_queue.put((True, final_message))
            else:
                final_message = "Échec sur toutes les machines"
                plugin_widget.set_status('error', final_message)
                await result_queue.put((False, final_message))
                
        except Exception as e:
            error_msg = f"Erreur lors de l'exécution SSH: {str(e)}"
            logger.error(error_msg)
            await result_queue.put((False, error_msg))