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

from ..utils.logging import get_logger
from ..utils.messaging import Message, MessageType, parse_message, create_info, create_error, create_success
from ..choice_screen.plugin_utils import get_plugin_folder_name
from .logger_utils import LoggerUtils
from .file_content_handler import FileContentHandler
from .root_credentials_manager import RootCredentialsManager
from ..ssh_manager.ssh_config_loader import SSHConfigLoader
from ..ssh_manager.ip_utils import get_target_ips

import pexpect

logger = get_logger('ssh_executor')

class SSHExecutor:
    """Classe pour l'exécution des plugins via SSH"""
    
    def __init__(self, app=None):
        """
        Initialise l'exécuteur SSH.
        
        Args:
            app (Optional[object]): L'application parente pour les logs et interactions
        """
        self.app = app
        
    def log_message(self, message: str, level: str = "info"):
        """
        Ajoute un message au log de l'application.
        
        Args:
            message (str): Le message à ajouter au log
            level (str): Le niveau de log (info, debug, error, success)
        """
        logger.debug(f"Ajout d'un message au log: {message} (niveau: {level})")
        try:
            # Créer une coroutine pour ajouter le message au log
            async def add_log_async():
                await LoggerUtils.add_log(self.app, message, level=level)
            
            # Exécuter la coroutine dans la boucle d'événements
            if self.app:
                asyncio.create_task(add_log_async())
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout du message au log: {e}")
    
    async def execute_plugin(self, plugin_widget, folder_name, config_dict: dict) -> Tuple[bool, str]:
        """
        Exécute un plugin via SSH sur une ou plusieurs machines.
        
        Args:
            plugin_widget: Widget du plugin pour les mises à jour de progression
            folder_name: Nom du dossier du plugin
            config_dict (dict): Dictionnaire de configuration complet du plugin
        
        Returns:
            Tuple[bool, str]: Succès de l'exécution et message de sortie consolidé
        """
        try:
            # Extraire les informations nécessaires du dictionnaire de configuration
            config = config_dict.get('config', {})
            plugin_name = config_dict.get('plugin_name', 'unknown_plugin')
            
            # Récupérer les informations SSH
            ssh_ips_str = config.get('ssh_ips', '')
            ssh_user = config.get('ssh_user', 'root')
            ssh_password = config.get('ssh_passwd', '')
            ssh_port = config.get('ssh_port', '22')
            
            # Vérifier si le plugin_widget a une IP cible spécifique
            # (cas où le widget a été créé pour une IP spécifique)
            if hasattr(plugin_widget, 'target_ip') and plugin_widget.target_ip:
                ssh_ip = plugin_widget.target_ip
                logger.debug(f"Utilisation de l'IP cible spécifique du widget: {ssh_ip}")
                
                # Exécuter sur cette IP spécifique
                return await self._execute_on_single_host(
                    ssh_ip, ssh_user, ssh_password, ssh_port,
                    plugin_widget, folder_name, plugin_name, config
                )
            
            # Sinon, utiliser l'IP ou les IPs de la configuration
            if not ssh_ips_str:
                return False, "Adresse IP SSH manquante"
            
            # Obtenir la liste des IPs cibles en tenant compte des exceptions
            ssh_exception_ips = config.get('ssh_exception_ips', '')
            target_ips = get_target_ips(ssh_ips_str, ssh_exception_ips)
            
            if not target_ips:
                return False, "Aucune adresse IP valide après filtrage des exceptions"
                
            logger.info(f"Exécution du plugin {plugin_name} sur {len(target_ips)} machines: {', '.join(target_ips)}")
            
            # Exécuter le plugin sur chaque IP cible
            results = []
            all_success = True
            
            # Mettre à jour le widget avec le nombre total de machines
            if plugin_widget:
                plugin_widget.update_progress(0.0, f"Préparation pour {len(target_ips)} machines...")
            
            # Informer l'utilisateur du début de l'exécution
            await LoggerUtils.add_log(self.app, f"Exécution du plugin {plugin_name} sur {len(target_ips)} machines", level="info")
            
            # Exécuter sur chaque machine
            unreachable_ips = []
            
            for i, ssh_ip in enumerate(target_ips):
                # Mettre à jour la progression
                if plugin_widget:
                    progress = (i / len(target_ips)) * 100
                    plugin_widget.update_progress(progress, f"Machine {i+1}/{len(target_ips)}: {ssh_ip}")
                
                try:
                    # Exécuter sur cette machine
                    success, output = await self._execute_on_single_host(
                        ssh_ip, ssh_user, ssh_password, ssh_port, 
                        plugin_widget, folder_name, plugin_name, config
                    )
                    
                    # Stocker le résultat
                    results.append({
                        'ip': ssh_ip,
                        'success': success,
                        'output': output
                    })
                    
                    # Mettre à jour le statut global
                    if not success:
                        all_success = False
                        # Détecter les machines injoignables
                        if "injoignable" in output or "No route to host" in output or "Timeout" in output:
                            unreachable_ips.append(ssh_ip)
                            logger.warning(f"Machine injoignable: {ssh_ip}")
                except Exception as e:
                    # Gérer les erreurs inattendues lors de l'exécution
                    error_msg = str(e)
                    logger.error(f"Erreur lors de l'exécution sur {ssh_ip}: {error_msg}")
                    await LoggerUtils.add_log(
                        self.app,
                        f"Erreur lors de l'exécution sur {ssh_ip}: {error_msg}",
                        level="error",
                        target_ip=ssh_ip
                    )
                    
                    results.append({
                        'ip': ssh_ip,
                        'success': False,
                        'output': f"Erreur: {error_msg}"
                    })
                    all_success = False
            
            # Ajouter un message spécifique pour les machines injoignables
            if unreachable_ips:
                unreachable_msg = f"Les machines suivantes sont injoignables: {', '.join(unreachable_ips)}"
                logger.error(unreachable_msg)
                await LoggerUtils.add_log(
                    self.app, 
                    unreachable_msg, 
                    level="error"
                )
            
            # Mettre à jour la progression finale
            if plugin_widget:
                if all_success:
                    plugin_widget.update_progress(100.0, f"Terminé sur {len(target_ips)} machines")
                else:
                    if unreachable_ips:
                        plugin_widget.update_progress(100.0, f"Terminé avec {len(unreachable_ips)} machines injoignables")
                    else:
                        plugin_widget.update_progress(100.0, f"Terminé avec erreurs sur certaines machines")
            
            # Consolider les résultats
            consolidated_output = self._consolidate_results(results)
            
            return all_success, consolidated_output
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Erreur globale lors de l'exécution du plugin {plugin_name}: {error_msg}")
            logger.error(traceback.format_exc())
            
            # Ajouter un message d'erreur spécifique dans les logs
            await LoggerUtils.add_log(
                self.app, 
                f"Erreur lors de l'exécution du plugin {plugin_name}: {error_msg}", 
                level="error"
            )
            
            return False, error_msg
            
    def _consolidate_results(self, results: List[Dict]) -> str:
        """
        Consolide les résultats d'exécution sur plusieurs machines.
        
        Args:
            results: Liste des résultats par machine
            
        Returns:
            str: Sortie consolidée
        """
        output = []
        
        # Compter les succès, échecs et machines injoignables
        success_count = sum(1 for r in results if r['success'])
        failure_count = len(results) - success_count
        unreachable_count = sum(1 for r in results if not r['success'] and 
                              ("injoignable" in r['output'] or "No route to host" in r['output'] or "Timeout" in r['output']))
        error_count = failure_count - unreachable_count
        
        # Ajouter un résumé
        if failure_count == 0:
            output.append(f"✅ Exécution réussie sur toutes les machines ({success_count})")
        else:
            summary = f"⚠️ Exécution réussie sur {success_count}/{len(results)} machines"
            if unreachable_count > 0:
                summary += f" ({unreachable_count} injoignables, {error_count} erreurs d'exécution)"
            output.append(summary)
        
        # Regrouper les résultats par statut
        success_results = [r for r in results if r['success']]
        unreachable_results = [r for r in results if not r['success'] and 
                              ("injoignable" in r['output'] or "No route to host" in r['output'] or "Timeout" in r['output'])]
        error_results = [r for r in results if not r['success'] and r not in unreachable_results]
        
        # Afficher d'abord les machines injoignables
        if unreachable_results:
            output.append(f"\n⚠️ MACHINES INJOIGNABLES ({len(unreachable_results)})")
            output.append(f"{'=' * 40}")
            for result in unreachable_results:
                output.append(f"❌ {result['ip']} - {result['output']}")
        
        # Afficher ensuite les machines avec erreurs
        if error_results:
            output.append(f"\n❌ MACHINES AVEC ERREURS ({len(error_results)})")
            output.append(f"{'=' * 40}")
            for result in error_results:
                ip = result['ip']
                result_output = result['output']
                
                # Limiter la taille de la sortie pour chaque machine
                if len(result_output) > 500:
                    result_output = result_output[:250] + "\n...\n" + result_output[-250:]
                    
                output.append(f"\n❌ Machine: {ip}")
                output.append(f"{'=' * 40}")
                output.append(result_output)
        
        # Afficher enfin les machines avec succès
        if success_results:
            output.append(f"\n✅ MACHINES AVEC SUCCÈS ({len(success_results)})")
            output.append(f"{'=' * 40}")
            for result in success_results:
                ip = result['ip']
                result_output = result['output']
                
                # Limiter la taille de la sortie pour chaque machine
                if len(result_output) > 500:
                    result_output = result_output[:250] + "\n...\n" + result_output[-250:]
                    
                output.append(f"\n✅ Machine: {ip}")
                output.append(f"{'=' * 40}")
                output.append(result_output)
            
        return "\n".join(output)
    
    async def _execute_on_single_host(
        self, ssh_ip: str, ssh_user: str, ssh_password: str, ssh_port: str,
        plugin_widget, folder_name: str, plugin_name: str, config: dict
    ) -> Tuple[bool, str]:
        """
        Exécute le plugin sur une seule machine distante.
        
        Args:
            ssh_ip: Adresse IP de la machine cible
            ssh_user: Nom d'utilisateur SSH
            ssh_password: Mot de passe SSH
            ssh_port: Port SSH
            plugin_widget: Widget du plugin pour les mises à jour de progression
            folder_name: Nom du dossier du plugin
            plugin_name: Nom du plugin
            config: Configuration du plugin
            
        Returns:
            Tuple[bool, str]: Succès de l'exécution et message de sortie
        """
        try:
            # Log de début d'exécution sur cette machine
            logger.info(f"Exécution du plugin {plugin_name} sur {ssh_ip}")
            await LoggerUtils.add_log(
                self.app, 
                f"Connexion à {ssh_ip} pour exécuter {plugin_name}...", 
                level="info",
                target_ip=ssh_ip
            )
            
            # Construire le chemin du plugin
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            plugin_dir = os.path.join(project_root, "plugins", folder_name)
            
            # Vérifier le type de plugin
            if os.path.exists(os.path.join(plugin_dir, "main.sh")):
                logger.info(f"Détecté comme plugin bash")
                is_bash_plugin = True
                exec_path = "main.sh"
            else:
                logger.info(f"Détecté comme plugin Python")
                is_bash_plugin = False
                exec_path = "exec.py"
            
            # Charger les paramètres du plugin
            settings_path = os.path.join(plugin_dir, "settings.yml")
            plugin_settings = {}
            if os.path.exists(settings_path):
                try:
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        yaml = YAML()
                        plugin_settings = yaml.load(f)
                    logger.debug(f"Paramètres du plugin chargés: {plugin_settings}")
                except Exception as e:
                    logger.error(f"Erreur lors de la lecture des paramètres du plugin: {e}")
            
            # Vérifier si le plugin nécessite des droits root
            needs_root = plugin_settings.get('ssh_root', False)
            logger.info(f"Plugin {folder_name} nécessite des droits root: {needs_root}")
            
            # Traiter le contenu des fichiers de configuration
            file_content = FileContentHandler.process_file_content(plugin_settings, config, plugin_dir)
            
            # Intégrer le contenu des fichiers dans la configuration
            for param_name, content in file_content.items():
                config[param_name] = content
                logger.info(f"Contenu du fichier intégré dans la configuration sous {param_name}")
            
            # Préparer le dossier distant
            remote_temp_dir = f"/tmp/pcutils_plugins/{folder_name}_{int(time.time())}"  
            logger.debug(f"Dossier distant: {remote_temp_dir}")
            
            # Préparer la commande d'exécution
            if is_bash_plugin:
                base_cmd = f"bash {exec_path} '{config.get('name', 'test')}' '{config.get('intensity', 'light')}'"
            else:
                # Sérialiser la configuration en JSON
                config_json = json.dumps(config).replace('"', '\\"')
                base_cmd = f"python3 {exec_path} \"{config_json}\""
            
            # Obtenir le gestionnaire d'identifiants root
            root_credentials_manager = RootCredentialsManager.get_instance()
            
            # Préparer les identifiants root si nécessaire
            if needs_root:
                root_credentials = root_credentials_manager.prepare_ssh_root_credentials(ssh_ip, config)
                logger.debug(f"Identifiants root préparés pour {ssh_ip}")
            
            # Vérifier d'abord si la machine est accessible
            try:
                # Utiliser ping pour vérifier si la machine est accessible
                ping_process = pexpect.spawn(f"ping -c 1 -W 3 {ssh_ip}", encoding='utf-8', timeout=5)
                i = ping_process.expect(['1 received', '0 received', pexpect.TIMEOUT, pexpect.EOF])
                
                if i == 1 or i == 2:  # 0 packets received ou timeout
                    error_msg = f"La machine {ssh_ip} est injoignable"
                    logger.error(error_msg)
                    await LoggerUtils.add_log(
                        self.app,
                        error_msg,
                        level="error",
                        target_ip=ssh_ip
                    )
                    return False, error_msg
                
                # Connexion et exécution via pexpect
                # Établir la connexion SSH
                ssh_process = pexpect.spawn(
                    f"ssh -p {ssh_port} {ssh_user}@{ssh_ip}", 
                    encoding='utf-8', 
                    timeout=30
                )
                
                # Gérer l'authentification
                i = ssh_process.expect(['password:', 'continue connecting', 'Connection refused', 'No route to host', 'Permission denied', pexpect.TIMEOUT, pexpect.EOF])
                
                if i == 0:  # Demande de mot de passe
                    ssh_process.sendline(ssh_password)
                    # Vérifier si le mot de passe est accepté
                    j = ssh_process.expect(['Permission denied', 'Last login', '$', '#', pexpect.TIMEOUT])
                    if j == 0:  # Mot de passe incorrect
                        error_msg = f"Authentification SSH refusée pour {ssh_user}@{ssh_ip} - Mot de passe incorrect"
                        logger.error(error_msg)
                        await LoggerUtils.add_log(
                            self.app,
                            error_msg,
                            level="error",
                            target_ip=ssh_ip
                        )
                        return False, error_msg
                elif i == 1:  # Confirmation de l'hôte
                    ssh_process.sendline('yes')
                    ssh_process.expect('password:')
                    ssh_process.sendline(ssh_password)
                    # Vérifier si le mot de passe est accepté
                    j = ssh_process.expect(['Permission denied', 'Last login', '$', '#', pexpect.TIMEOUT])
                    if j == 0:  # Mot de passe incorrect
                        error_msg = f"Authentification SSH refusée pour {ssh_user}@{ssh_ip} - Mot de passe incorrect"
                        logger.error(error_msg)
                        await LoggerUtils.add_log(
                            self.app,
                            error_msg,
                            level="error",
                            target_ip=ssh_ip
                        )
                        return False, error_msg
                elif i == 2:  # Connexion refusée
                    error_msg = f"Connexion SSH refusée pour {ssh_ip} - Le service SSH n'est peut-être pas actif"
                    logger.error(error_msg)
                    await LoggerUtils.add_log(
                        self.app,
                        error_msg,
                        level="error",
                        target_ip=ssh_ip
                    )
                    return False, error_msg
                elif i == 3:  # Pas de route vers l'hôte
                    error_msg = f"Impossible d'atteindre {ssh_ip} - Pas de route vers l'hôte"
                    logger.error(error_msg)
                    await LoggerUtils.add_log(
                        self.app,
                        error_msg,
                        level="error",
                        target_ip=ssh_ip
                    )
                    return False, error_msg
                elif i == 4:  # Permission refusée
                    error_msg = f"Authentification SSH refusée pour {ssh_user}@{ssh_ip}"
                    logger.error(error_msg)
                    await LoggerUtils.add_log(
                        self.app,
                        error_msg,
                        level="error",
                        target_ip=ssh_ip
                    )
                    return False, error_msg
                elif i == 5 or i == 6:  # Timeout ou EOF
                    error_msg = f"Timeout lors de la connexion SSH à {ssh_ip}"
                    logger.error(error_msg)
                    await LoggerUtils.add_log(
                        self.app,
                        error_msg,
                        level="error",
                        target_ip=ssh_ip
                    )
                    return False, error_msg
                
                # Créer le dossier distant et copier les fichiers
                ssh_process.sendline(f"mkdir -p {remote_temp_dir}")
                
                # Transférer les fichiers via SCP
                # Utiliser /* pour copier le contenu du dossier et non le dossier lui-même
                scp_process = pexpect.spawn(
                    f"scp -r {plugin_dir}/* {ssh_user}@{ssh_ip}:{remote_temp_dir}/", 
                    encoding='utf-8', 
                    timeout=30
                )
                
                # Gérer l'authentification SCP
                i = scp_process.expect(['password:', 'continue connecting', 'No such file or directory', 'Permission denied', pexpect.TIMEOUT, pexpect.EOF])
                
                if i == 0:  # Demande de mot de passe
                    scp_process.sendline(ssh_password)
                    # Vérifier si le transfert réussit
                    j = scp_process.expect(['Permission denied', 'No such file or directory', '100%', pexpect.TIMEOUT, pexpect.EOF])
                    if j == 0:  # Mot de passe incorrect
                        error_msg = f"Authentification SCP refusée pour {ssh_user}@{ssh_ip} - Mot de passe incorrect"
                        logger.error(error_msg)
                        await LoggerUtils.add_log(
                            self.app,
                            error_msg,
                            level="error",
                            target_ip=ssh_ip
                        )
                        return False, error_msg
                    elif j == 1:  # Fichier ou répertoire introuvable
                        error_msg = f"Erreur SCP: Fichier ou répertoire introuvable lors du transfert vers {ssh_ip}"
                        logger.error(error_msg)
                        await LoggerUtils.add_log(
                            self.app,
                            error_msg,
                            level="error",
                            target_ip=ssh_ip
                        )
                        return False, error_msg
                elif i == 1:  # Confirmation de l'hôte
                    scp_process.sendline('yes')
                    scp_process.expect('password:')
                    scp_process.sendline(ssh_password)
                    # Vérifier si le transfert réussit
                    j = scp_process.expect(['Permission denied', 'No such file or directory', '100%', pexpect.TIMEOUT, pexpect.EOF])
                    if j == 0 or j == 1:  # Erreur de permission ou fichier introuvable
                        error_msg = f"Erreur lors du transfert SCP vers {ssh_ip}"
                        logger.error(error_msg)
                        await LoggerUtils.add_log(
                            self.app,
                            error_msg,
                            level="error",
                            target_ip=ssh_ip
                        )
                        return False, error_msg
                elif i == 2:  # Fichier ou répertoire introuvable
                    error_msg = f"Erreur SCP: Fichier ou répertoire introuvable lors du transfert vers {ssh_ip}"
                    logger.error(error_msg)
                    await LoggerUtils.add_log(
                        self.app,
                        error_msg,
                        level="error",
                        target_ip=ssh_ip
                    )
                    return False, error_msg
                elif i == 3:  # Permission refusée
                    error_msg = f"Erreur SCP: Permission refusée lors du transfert vers {ssh_ip}"
                    logger.error(error_msg)
                    await LoggerUtils.add_log(
                        self.app,
                        error_msg,
                        level="error",
                        target_ip=ssh_ip
                    )
                    return False, error_msg
                elif i == 4:  # Timeout
                    error_msg = f"Timeout lors du transfert SCP vers {ssh_ip}"
                    logger.error(error_msg)
                    await LoggerUtils.add_log(
                        self.app,
                        error_msg,
                        level="error",
                        target_ip=ssh_ip
                    )
                    return False, error_msg
                
                # Attendre la fin du transfert
                try:
                    scp_process.expect(pexpect.EOF, timeout=60)
                except pexpect.TIMEOUT:
                    error_msg = f"Timeout lors du transfert SCP vers {ssh_ip}"
                    logger.error(error_msg)
                    await LoggerUtils.add_log(
                        self.app,
                        error_msg,
                        level="error",
                        target_ip=ssh_ip
                    )
                    return False, error_msg
                
                # Vérifier que le fichier exec.py a bien été copié
                ssh_process.sendline(f"ls -la {remote_temp_dir}")
                ssh_process.expect(remote_temp_dir)
                ls_output = ssh_process.before + ssh_process.after
                logger.debug(f"Contenu du dossier distant: {ls_output}")
                
                # Vérifier que le fichier d'exécution existe
                exec_file = "main.sh" if is_bash_plugin else "exec.py"
                ssh_process.sendline(f"test -f {remote_temp_dir}/{exec_file} && echo 'FILE_EXISTS' || echo 'FILE_MISSING'")
                i = ssh_process.expect(['FILE_EXISTS', 'FILE_MISSING', pexpect.TIMEOUT])
                
                if i == 1:  # Fichier manquant
                    error_msg = f"Le fichier {exec_file} est manquant sur la machine distante {ssh_ip}"
                    logger.error(error_msg)
                    await LoggerUtils.add_log(
                        self.app,
                        error_msg,
                        level="error",
                        target_ip=ssh_ip
                    )
                    return False, error_msg
                elif i == 2:  # Timeout
                    error_msg = f"Timeout lors de la vérification du fichier {exec_file} sur {ssh_ip}"
                    logger.error(error_msg)
                    await LoggerUtils.add_log(
                        self.app,
                        error_msg,
                        level="error",
                        target_ip=ssh_ip
                    )
                    return False, error_msg
                
                # Changer de répertoire et exécuter la commande
                if needs_root:
                    # Utiliser sudo si nécessaire
                    ssh_process.sendline(f"cd {remote_temp_dir} && sudo {base_cmd}")
                    i = ssh_process.expect(['password for', pexpect.TIMEOUT])
                    if i == 0:
                        ssh_process.sendline(root_credentials.get('password', ''))
                else:
                    ssh_process.sendline(f"cd {remote_temp_dir} && {base_cmd}")
                
                # Capturer la sortie
                output = ""
                while True:
                    try:
                        i = ssh_process.expect([pexpect.TIMEOUT, pexpect.EOF, '\n'], timeout=5)
                        if i == 0:
                            break  # Timeout
                        elif i == 1:
                            break  # EOF
                        else:
                            line = ssh_process.before.strip()
                            output += line + "\n"
                            
                            # Traiter la ligne en temps réel
                            try:
                                await LoggerUtils.process_output_line(
                                    self.app, 
                                    line, 
                                    plugin_widget,
                                    target_ip=ssh_ip
                                )
                            except Exception as log_error:
                                logger.error(f"Erreur de traitement de log: {log_error}")
                    except Exception as e:
                        logger.warning(f"Erreur lors de la lecture de la sortie: {e}")
                        break
                
                # Vérifier le code de retour
                ssh_process.sendline("echo $?")
                i = ssh_process.expect(['\d+', pexpect.TIMEOUT])
                return_code = int(ssh_process.match.group(0)) if i == 0 else 1
                
                # Nettoyer le dossier temporaire
                ssh_process.sendline(f"rm -rf {remote_temp_dir}")
                
                # Fermer la connexion
                ssh_process.sendline("exit")
                ssh_process.expect(pexpect.EOF)
                
                # Déterminer le succès
                success = return_code == 0
                
                # Journaliser le résultat
                if success:
                    logger.info(f"Plugin {folder_name} exécuté avec succès sur {ssh_ip}")
                    await LoggerUtils.add_log(
                        self.app, 
                        f"Plugin {folder_name} exécuté avec succès", 
                        level="success",
                        target_ip=ssh_ip
                    )
                    return True, output
                else:
                    logger.error(f"Échec de l'exécution du plugin {folder_name} sur {ssh_ip}")
                    await LoggerUtils.add_log(
                        self.app, 
                        f"Échec de l'exécution du plugin {folder_name} (code retour: {return_code})", 
                        level="error",
                        target_ip=ssh_ip
                    )
                    return False, output
                
            except Exception as ssh_error:
                error_msg = str(ssh_error)
                logger.error(f"Erreur SSH lors de l'exécution de {folder_name} sur {ssh_ip}: {error_msg}")
                
                # Détection des erreurs spécifiques
                if "No route to host" in error_msg or "Connection refused" in error_msg or "timed out" in error_msg:
                    error_msg = f"Impossible de se connecter à l'hôte {ssh_ip}: hôte injoignable ou connexion refusée"
                    await LoggerUtils.add_log(self.app, error_msg, level="error", target_ip=ssh_ip)
                elif "No such file or directory" in error_msg:
                    error_msg = f"Fichier ou répertoire introuvable sur {ssh_ip}: vérifiez que le plugin est correctement installé"
                    await LoggerUtils.add_log(self.app, error_msg, level="error", target_ip=ssh_ip)
                elif "Permission denied" in error_msg:
                    error_msg = f"Accès refusé sur {ssh_ip}: vérifiez les droits d'accès"
                    await LoggerUtils.add_log(self.app, error_msg, level="error", target_ip=ssh_ip)
                else:
                    await LoggerUtils.add_log(self.app, f"Erreur lors de l'exécution sur {ssh_ip}: {error_msg}", level="error", target_ip=ssh_ip)
                    
                return False, error_msg
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Erreur globale lors de l'exécution du plugin {plugin_name}: {error_msg}")
            logger.error(traceback.format_exc())
            
            # Ajouter un message d'erreur spécifique dans les logs
            await LoggerUtils.add_log(
                self.app, 
                f"Erreur lors de l'exécution du plugin {plugin_name}: {error_msg}", 
                level="error"
            )
            
            return False, error_msg