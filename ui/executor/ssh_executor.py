"""
Module pour l'exécution des plugins via SSH.
"""

import os
import json
import time
import asyncio
import ipaddress
import pexpect
from typing import List, Tuple

from .logger_utils import LoggerUtils
from ..logging import get_logger

logger = get_logger('ssh_executor')

class SSHExecutor:
    """Classe pour l'exécution des plugins via SSH"""
    
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
            await LoggerUtils.add_log(app, f"Test de connectivité pour {ip_address}...", "debug")
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
            await LoggerUtils.add_log(app, f"Connexion SSH à {ip_address}...", "info")
            
            # Créer le processus SSH avec pexpect
            ssh_command = f"ssh {username}@{ip_address}"
            ssh_process = pexpect.spawn(ssh_command, encoding='utf-8')
            
            # Gérer l'authentification
            i = ssh_process.expect(['password:', 'continue connecting', pexpect.TIMEOUT, pexpect.EOF], timeout=10)
            if i == 0:
                ssh_process.sendline(password)
            elif i == 1:
                ssh_process.sendline('yes')
                ssh_process.expect('password:')
                ssh_process.sendline(password)
            else:
                return False, f"Erreur de connexion à {ip_address}"
            
            # Vérifier l'authentification
            i = ssh_process.expect(['$', '#', pexpect.TIMEOUT, pexpect.EOF], timeout=10)
            if i >= 2:
                return False, f"Échec de l'authentification sur {ip_address}"
            
            await LoggerUtils.add_log(app, f"Connexion établie avec {ip_address}", "success")
            
            # Créer un répertoire temporaire
            temp_dir = f"/tmp/pcutils_{plugin_id}_{int(time.time())}"
            ssh_process.sendline(f"mkdir -p {temp_dir}")
            ssh_process.expect(['$', '#'])
            
            # Transférer les fichiers (utiliser un autre processus pexpect pour scp)
            await LoggerUtils.add_log(app, f"Transfert des fichiers vers {ip_address}...", "info")
            scp_command = f"scp -r {plugin_dir}/* {username}@{ip_address}:{temp_dir}/"
            scp_process = pexpect.spawn(scp_command, encoding='utf-8')
            i = scp_process.expect(['password:', pexpect.TIMEOUT, pexpect.EOF], timeout=30)
            if i == 0:
                scp_process.sendline(password)
            
            # Attendre la fin du transfert
            scp_process.expect(pexpect.EOF, timeout=60)
            await LoggerUtils.add_log(app, f"Transfert terminé vers {ip_address}", "success")
            
            # Identifier le type de plugin
            is_bash_plugin = os.path.exists(os.path.join(plugin_dir, "main.sh"))
            
            # Exécuter le plugin
            if is_bash_plugin:
                cmd = f"cd {temp_dir} && bash main.sh '{plugin_config.get('name', 'test')}' '{plugin_config.get('intensity', 'light')}'"
            else:
                # Pour un plugin Python, convertir la config en JSON
                json_config = json.dumps(plugin_config).replace("'", "\\'")
                cmd = f"cd {temp_dir} && python3 exec.py '{json_config}'"
            
            await LoggerUtils.add_log(app, f"Exécution du plugin sur {ip_address}...", "info")
            ssh_process.sendline(cmd)
            
            # Attendre et traiter la sortie ligne par ligne
            output = ""
            while True:
                try:
                    i = ssh_process.expect(['\n', pexpect.TIMEOUT, pexpect.EOF], timeout=1)
                    if i == 0:
                        line = ssh_process.before
                        if line:
                            # Traiter la ligne pour mettre à jour l'UI
                            await SSHExecutor.handle_ssh_output(app, line, ip_address)
                            output += line + "\n"
                    elif i >= 1:
                        break
                except Exception as e:
                    logger.error(f"Erreur de lecture SSH: {str(e)}")
                    break
            
            # Nettoyer les fichiers temporaires
            ssh_process.sendline(f"rm -rf {temp_dir}")
            ssh_process.sendline("exit")
            
            # Vérifier si l'exécution s'est bien passée
            success = "Exécution terminée avec succès" in output or "Progression : 100%" in output
            
            if success:
                return True, "Exécution SSH terminée avec succès"
            else:
                return False, "Erreur lors de l'exécution SSH"
                
        except Exception as e:
            logger.error(f"Erreur SSH: {str(e)}")
            return False, f"Erreur SSH: {str(e)}"
    
    @staticmethod
    async def handle_ssh_output(app, line, ip_address=None):
        """Traite la sortie SSH pour la mise à jour de l'UI"""
        try:
            # Ajouter l'adresse IP au début de la ligne si fournie
            log_line = line.strip() if line else ""
            if ip_address and log_line:
                log_line = f"[{ip_address}] {log_line}"
            
            # Détecter le niveau de log (error, warning, info, etc.)
            level = "info"
            if "[ERROR]" in log_line:
                level = "error"
            elif "[WARNING]" in log_line:
                level = "warning"
            elif "[DEBUG]" in log_line:
                level = "debug"
            elif "[SUCCESS]" in log_line:
                level = "success"
            elif "permission denied" in log_line.lower():
                # Capture explicite des erreurs de permission
                level = "error"
            elif "error" in log_line.lower():
                # Capture générique des erreurs
                level = "error"
            
            # Ajouter au log avec gestion des erreurs
            if log_line:
                await LoggerUtils.add_log(app, log_line, level)
        except Exception as e:
            # En cas d'erreur lors du traitement, logger l'erreur directement
            logger.error(f"Erreur lors du traitement de la sortie SSH: {str(e)}")
            try:
                # Tenter de logger une version simplifiée du message
                await LoggerUtils.add_log(app, f"Sortie SSH (non formatée): {type(line)}", "error")
            except:
                pass  # Si même cela échoue, abandonner silencieusement
    
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
            
            await LoggerUtils.add_log(app, f"Mode SSH activé pour {plugin_show_name}", "info")
            
            # Construire le chemin du plugin
            plugin_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "plugins", folder_name)
            
            # Résoudre et filtrer les IPs
            plugin_widget.update_progress(0.1, "Recherche des machines accessibles...")
            valid_ips, excluded_ips = await SSHExecutor.resolve_ips(app, ssh_ips, ssh_exception_ips)
            
            if excluded_ips:
                await LoggerUtils.add_log(app, f"IPs exclues: {', '.join(excluded_ips)}", "info")
            
            if not valid_ips:
                error_msg = "Aucune machine accessible trouvée"
                plugin_widget.set_status('error', error_msg)
                await LoggerUtils.add_log(app, error_msg, "error")
                await result_queue.put((False, error_msg))
                return
            
            await LoggerUtils.add_log(app, f"Machines accessibles: {', '.join(valid_ips)}", "info")
            
            # Exécution sur chaque IP valide
            total_ips = len(valid_ips)
            success_count = 0
            
            for idx, ip in enumerate(valid_ips):
                ip_progress = 0.1 + (0.9 * idx / total_ips)
                plugin_widget.update_progress(ip_progress, f"Connexion à {ip}...")
                
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
                
                if success:
                    success_count += 1
                    await LoggerUtils.add_log(app, f"Exécution réussie sur {ip}", "success")
                else:
                    await LoggerUtils.add_log(app, f"Échec sur {ip}: {message}", "error")
            
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