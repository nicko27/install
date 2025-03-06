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

from ..utils.logging import get_logger
from ..utils.messaging import Message, MessageType, parse_message
from ..ssh_manager.ssh_config_loader import SSHConfigLoader
from .logger_utils import LoggerUtils

logger = get_logger('ssh_executor')

class SSHExecutor:
    """Classe pour l'exécution des plugins via SSH"""
    
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
        """Teste si une IP répond au ping"""
        try:
            # Utiliser un timeout court pour éviter d'attendre trop longtemps
            debug_msg = Message(MessageType.DEBUG, f"Test de connectivité pour {ip_address}...")
            await LoggerUtils.display_message(app, debug_msg)
            
            process = await asyncio.create_subprocess_exec(
                "ping", "-c", "1", "-W", "1", ip_address,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            return await process.wait() == 0
        except Exception as e:
            logger.error(f"Erreur lors du ping de {ip_address}: {str(e)}")
            return False
    
    @staticmethod
    async def execute_ssh(app, ip_address, username, password, plugin_dir, plugin_id, plugin_config):
        """Exécute un plugin via SSH sur une machine distante"""
        try:
            # Vérifier si on doit utiliser l'exécution locale
            if SSHConfigLoader.get_instance().should_use_local_execution(ip_address):
                info_msg = Message(MessageType.INFO, f"Utilisation de l'exécution locale pour {ip_address}")
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
            ssh_config = SSHConfigLoader.get_instance()
            connection_config = ssh_config.get_connection_config()
            auth_config = ssh_config.get_authentication_config()
            
            # Récupérer les timeouts depuis la configuration
            connect_timeout = connection_config.get('connect_timeout', 10)
            transfer_timeout = connection_config.get('transfer_timeout', 60)
            command_timeout = connection_config.get('command_timeout', 120)
            
            # Informer de la connexion SSH
            info_msg = Message(MessageType.INFO, f"Connexion SSH à {ip_address}...")
            await LoggerUtils.display_message(app, info_msg)
            
            # Créer le processus SSH avec pexpect
            ssh_command = f"ssh {username}@{ip_address}"
            ssh_process = pexpect.spawn(ssh_command, encoding='utf-8')
            
            # Gérer l'authentification
            i = ssh_process.expect(['password:', 'continue connecting', pexpect.TIMEOUT, pexpect.EOF], timeout=connect_timeout)
            if i == 0:
                ssh_process.sendline(password)
            elif i == 1:
                # Auto-accepter la clé d'hôte si configuré
                if auth_config.get('auto_add_keys', True):
                    ssh_process.sendline('yes')
                    ssh_process.expect('password:')
                    ssh_process.sendline(password)
                else:
                    return False, f"Nouvelle clé d'hôte détectée pour {ip_address}, mais l'acceptation automatique est désactivée"
            else:
                return False, f"Erreur de connexion à {ip_address} (timeout: {connect_timeout}s)"
            
            # Vérifier l'authentification
            i = ssh_process.expect(['$', '#', pexpect.TIMEOUT, pexpect.EOF], timeout=connect_timeout)
            if i >= 2:
                return False, f"Échec de l'authentification sur {ip_address}"
            
            # Connexion établie
            success_msg = Message(MessageType.SUCCESS, f"Connexion établie avec {ip_address}")
            await LoggerUtils.display_message(app, success_msg)
            
            # Obtenir les paramètres d'exécution
            execution_config = ssh_config.get_execution_config()
            remote_temp_dir = execution_config.get('remote_temp_dir', '/tmp/pcutils')
            cleanup_temp_files = execution_config.get('cleanup_temp_files', True)
            
            # Créer un répertoire temporaire
            temp_dir = f"{remote_temp_dir}_{plugin_id}_{int(time.time())}"
            ssh_process.sendline(f"mkdir -p {temp_dir}")
            ssh_process.expect(['$', '#'])
            
            # Transférer les fichiers (utiliser un autre processus pexpect pour scp)
            info_msg = Message(MessageType.INFO, f"Transfert des fichiers vers {ip_address}...")
            await LoggerUtils.display_message(app, info_msg)
            
            scp_command = f"scp -r {plugin_dir}/* {username}@{ip_address}:{temp_dir}/"
            scp_process = pexpect.spawn(scp_command, encoding='utf-8')
            i = scp_process.expect(['password:', pexpect.TIMEOUT, pexpect.EOF], timeout=connect_timeout)
            if i == 0:
                scp_process.sendline(password)
            
            # Attendre la fin du transfert
            scp_process.expect(pexpect.EOF, timeout=transfer_timeout)
            
            success_msg = Message(MessageType.SUCCESS, f"Transfert terminé vers {ip_address}")
            await LoggerUtils.display_message(app, success_msg)
            
            # Identifier le type de plugin
            is_bash_plugin = os.path.exists(os.path.join(plugin_dir, "main.sh"))
            
            # Exécuter le plugin
            if is_bash_plugin:
                cmd = f"cd {temp_dir} && bash main.sh '{plugin_config.get('name', 'test')}' '{plugin_config.get('intensity', 'light')}'"
            else:
                # Pour un plugin Python, convertir la config en JSON
                json_config = json.dumps(plugin_config).replace("'", "\\'")
                cmd = f"cd {temp_dir} && python3 exec.py '{json_config}'"
            
            info_msg = Message(MessageType.INFO, f"Exécution du plugin sur {ip_address}...")
            await LoggerUtils.display_message(app, info_msg)
            
            ssh_process.sendline(cmd)
            
            # Attendre et traiter la sortie ligne par ligne
            output = ""
            while True:
                try:
                    i = ssh_process.expect(['\n', pexpect.TIMEOUT, pexpect.EOF], timeout=1)
                    if i == 0:
                        line = ssh_process.before
                        if line:
                            # Traiter la ligne avec préfixe IP
                            await SSHExecutor.process_ssh_output(app, line, ip_address, plugin_widget)
                            output += line + "\n"
                    elif i >= 1:
                        break
                except Exception as e:
                    logger.error(f"Erreur de lecture SSH: {str(e)}")
                    break
            
            # Nettoyer les fichiers temporaires si configuré
            if cleanup_temp_files:
                ssh_process.sendline(f"rm -rf {temp_dir}")
            ssh_process.sendline("exit")
            
            # Vérifier si l'exécution s'est bien passée
            success = "Exécution terminée avec succès" in output or "Progression : 100%" in output
            
            # Journaliser la sortie complète si configuré
            if ssh_config.get_logging_config().get('log_full_output', False):
                logger.debug(f"Sortie complète de l'exécution SSH sur {ip_address}:\n{output}")
            
            if success:
                return True, "Exécution SSH terminée avec succès"
            else:
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
            error_msg = Message(MessageType.ERROR, f"Erreur de traitement SSH: {str(e)}")
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
            
            info_msg = Message(MessageType.INFO, f"Mode SSH activé pour {plugin_show_name}")
            await LoggerUtils.display_message(app, info_msg)
            
            # Construire le chemin du plugin
            plugin_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "plugins", folder_name)
            
            # Résoudre et filtrer les IPs
            plugin_widget.update_progress(0.1, "Recherche des machines accessibles...")
            valid_ips, excluded_ips = await SSHExecutor.resolve_ips(app, ssh_ips, ssh_exception_ips)
            
            if excluded_ips:
                info_msg = Message(MessageType.INFO, f"IPs exclues: {', '.join(excluded_ips)}")
                await LoggerUtils.display_message(app, info_msg)
            
            if not valid_ips:
                error_msg = Message(MessageType.ERROR, "Aucune machine accessible trouvée")
                await LoggerUtils.display_message(app, error_msg)
                plugin_widget.set_status('error', "Aucune machine accessible")
                await result_queue.put((False, "Aucune machine accessible trouvée"))
                return
            
            info_msg = Message(MessageType.INFO, f"Machines accessibles: {', '.join(valid_ips)}")
            await LoggerUtils.display_message(app, info_msg)
            
            # Obtenir la configuration d'exécution
            ssh_config = SSHConfigLoader.get_instance()
            execution_config = ssh_config.get_execution_config()
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
                plugin_config.update({
                    "ssh_mode": True,
                    "ssh_ips": ssh_ips,
                    "ssh_current_ip": ip,
                    "ssh_user": ssh_user,
                    "ssh_passwd": ssh_passwd,
                    "ssh_exception_ips": ssh_exception_ips,
                    "ssh_sms_enabled": ssh_sms_enabled,
                    "ssh_sms": ssh_sms if ssh_sms_enabled else ""
                })
                
                # Exécuter sur cette IP
                success, message = await SSHExecutor.execute_ssh(
                    app, ip, ssh_user, ssh_passwd, plugin_dir, plugin_id, plugin_config
                )
                
                # Mettre à jour la progression
                plugin_widget.update_progress(progress_end, f"Terminé sur {ip}")
                
                if success:
                    success_count += 1
                    await LoggerUtils.display_message(app, Message(MessageType.SUCCESS, f"Exécution réussie sur {ip}"))
                else:
                    await LoggerUtils.display_message(app, Message(MessageType.ERROR, f"Échec sur {ip}: {message}"))
                
                return success, message
            
            # Exécution parallèle ou séquentielle selon la configuration
            if parallel_execution and total_ips > 1:
                info_msg = Message(MessageType.INFO, f"Exécution parallèle sur {min(total_ips, max_parallel)} machines")
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