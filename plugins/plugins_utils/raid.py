#!/usr/bin/env python3
"""
Module utilitaire pour la gestion avancée des tableaux RAID sous Linux.
Permet de créer, gérer, surveiller et réparer les dispositifs RAID.
"""

from .commands import Commands
import os
import re
import time
import tempfile
from typing import Union, Optional, List, Dict, Any, Tuple


class RaidCommands(Commands):
    """
    Classe pour gérer les tableaux RAID Linux (mdadm).
    Hérite de la classe Commands pour la gestion des commandes système.
    """
    
    def __init__(self, logger=None, target_ip=None):
        """
        Initialise le gestionnaire RAID.

        Args:
            logger: Instance de PluginLogger à utiliser
            target_ip: Adresse IP cible pour les logs (optionnel, pour les exécutions SSH)
        """
        super().__init__(logger, target_ip)

    def create_raid_array(self, raid_level, devices, array_name=None, spare_devices=None, chunk_size=None, metadata=None):
        """
        Crée un nouveau tableau RAID.

        Args:
            raid_level: Niveau RAID (0, 1, 4, 5, 6, 10)
            devices: Liste des périphériques à utiliser
            array_name: Nom de l'array (optionnel, md0 par défaut)
            spare_devices: Liste des périphériques de secours (optionnel)
            chunk_size: Taille de chunk en KB (optionnel)
            metadata: Version des métadonnées (optionnel)

        Returns:
            bool: True si la création a réussi, False sinon
        """
        if not devices or len(devices) < 2:
            self.log_error("Au moins deux périphériques sont nécessaires pour créer un RAID")
            return False

        # Déterminer le nom du tableau
        if not array_name:
            # Trouver le prochain md disponible
            md_num = 0
            while os.path.exists(f"/dev/md{md_num}"):
                md_num += 1
            array_name = f"md{md_num}"
        elif not array_name.startswith("md"):
            array_name = f"md{array_name}"

        # Construire la commande
        cmd = ['mdadm', '--create', f"/dev/{array_name}", f"--level={raid_level}", f"--raid-devices={len(devices)}"]

        # Options supplémentaires
        if chunk_size:
            cmd.append(f"--chunk={chunk_size}")

        if metadata:
            cmd.append(f"--metadata={metadata}")

        # Ajouter les périphériques
        cmd.extend(devices)

        # Ajouter les disques de secours si spécifiés
        if spare_devices:
            cmd.append(f"--spare-devices={len(spare_devices)}")
            cmd.extend(spare_devices)

        self.log_info(f"Création du tableau RAID {raid_level} '{array_name}' avec les périphériques: {', '.join(devices)}")

        # Exécuter la commande avec --run pour forcer la création même en cas de superblocks
        cmd.append("--run")
        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Tableau RAID {raid_level} '{array_name}' créé avec succès")

            # Mise à jour de mdadm.conf pour la persistance
            self._update_mdadm_conf()

            return True
        else:
            # Si l'erreur mentionne des superblocks, essayer avec --force
            if "appears to contain an ext2fs" in stderr or "superblock" in stderr:
                self.log_warning("Détection de superblocks sur les périphériques, tentative avec --force")
                cmd.append("--force")
                force_success, _, force_stderr = self.run_as_root(cmd)

                if force_success:
                    self.log_success(f"Tableau RAID {raid_level} '{array_name}' créé avec succès (avec --force)")
                    self._update_mdadm_conf()
                    return True
                else:
                    self.log_error(f"Échec de la création du tableau RAID (même avec --force): {force_stderr}")
                    return False
            else:
                self.log_error(f"Échec de la création du tableau RAID: {stderr}")
                return False

    def stop_raid_array(self, array_name):
        """
        Arrête un tableau RAID.

        Args:
            array_name: Nom du tableau RAID à arrêter

        Returns:
            bool: True si l'arrêt a réussi, False sinon
        """
        # Normaliser le nom du tableau
        if not array_name.startswith("/dev/"):
            if not array_name.startswith("md"):
                array_name = f"md{array_name}"
            array_path = f"/dev/{array_name}"
        else:
            array_path = array_name
            array_name = os.path.basename(array_path)

        # Vérifier si le tableau existe
        if not os.path.exists(array_path):
            self.log_error(f"Le tableau RAID '{array_name}' n'existe pas")
            return False

        # Vérifier si le tableau est monté
        if self._is_mounted(array_path):
            self.log_warning(f"Le tableau RAID '{array_name}' est monté. Tentative de démontage.")
            umount_cmd = ['umount', array_path]
            umount_success, _, umount_stderr = self.run_as_root(umount_cmd)

            if not umount_success:
                self.log_error(f"Impossible de démonter '{array_path}': {umount_stderr}")
                return False

        self.log_info(f"Arrêt du tableau RAID '{array_name}'")

        # Arrêter le tableau
        cmd = ['mdadm', '--stop', array_path]
        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Tableau RAID '{array_name}' arrêté avec succès")
            return True
        else:
            self.log_error(f"Échec de l'arrêt du tableau RAID '{array_name}': {stderr}")
            return False

    def add_device_to_raid(self, array_name, device):
        """
        Ajoute un périphérique à un tableau RAID.

        Args:
            array_name: Nom du tableau RAID
            device: Périphérique à ajouter

        Returns:
            bool: True si l'ajout a réussi, False sinon
        """
        # Normaliser le nom du tableau
        if not array_name.startswith("/dev/"):
            if not array_name.startswith("md"):
                array_name = f"md{array_name}"
            array_path = f"/dev/{array_name}"
        else:
            array_path = array_name
            array_name = os.path.basename(array_path)

        # Vérifier si le tableau existe
        if not os.path.exists(array_path):
            self.log_error(f"Le tableau RAID '{array_name}' n'existe pas")
            return False

        self.log_info(f"Ajout du périphérique '{device}' au tableau RAID '{array_name}'")

        # Ajouter le périphérique
        cmd = ['mdadm', '--add', array_path, device]
        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Périphérique '{device}' ajouté avec succès au tableau RAID '{array_name}'")
            return True
        else:
            self.log_error(f"Échec de l'ajout du périphérique '{device}': {stderr}")
            return False

    def remove_device_from_raid(self, array_name, device, fail_first=True):
        """
        Retire un périphérique d'un tableau RAID.

        Args:
            array_name: Nom du tableau RAID
            device: Périphérique à retirer
            fail_first: Si True, marque d'abord le périphérique comme défaillant

        Returns:
            bool: True si le retrait a réussi, False sinon
        """
        # Normaliser le nom du tableau
        if not array_name.startswith("/dev/"):
            if not array_name.startswith("md"):
                array_name = f"md{array_name}"
            array_path = f"/dev/{array_name}"
        else:
            array_path = array_name
            array_name = os.path.basename(array_path)

        # Vérifier si le tableau existe
        if not os.path.exists(array_path):
            self.log_error(f"Le tableau RAID '{array_name}' n'existe pas")
            return False

        # Marquer le périphérique comme défaillant d'abord si demandé
        if fail_first:
            self.log_info(f"Marquage du périphérique '{device}' comme défaillant dans le tableau RAID '{array_name}'")
            fail_cmd = ['mdadm', '--fail', array_path, device]
            fail_success, _, fail_stderr = self.run_as_root(fail_cmd)

            if not fail_success:
                self.log_warning(f"Impossible de marquer le périphérique '{device}' comme défaillant: {fail_stderr}")
                # Continuer quand même avec le retrait

        self.log_info(f"Retrait du périphérique '{device}' du tableau RAID '{array_name}'")

        # Retirer le périphérique
        cmd = ['mdadm', '--remove', array_path, device]
        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Périphérique '{device}' retiré avec succès du tableau RAID '{array_name}'")
            return True
        else:
            self.log_error(f"Échec du retrait du périphérique '{device}': {stderr}")
            return False

    def check_raid_status(self, array_name=None):
        """
        Vérifie l'état d'un ou tous les tableaux RAID.

        Args:
            array_name: Nom du tableau RAID (optionnel, tous si None)

        Returns:
            dict or list: Informations sur l'état du RAID
        """
        if array_name:
            # Normaliser le nom du tableau
            if not array_name.startswith("/dev/"):
                if not array_name.startswith("md"):
                    array_name = f"md{array_name}"
                array_path = f"/dev/{array_name}"
            else:
                array_path = array_name
                array_name = os.path.basename(array_path)

            # Vérifier si le tableau existe
            if not os.path.exists(array_path):
                self.log_error(f"Le tableau RAID '{array_name}' n'existe pas")
                return None

            self.log_info(f"Vérification de l'état du tableau RAID '{array_name}'")

            # Obtenir l'état détaillé
            cmd = ['mdadm', '--detail', array_path]
            success, stdout, stderr = self.run_as_root(cmd, no_output=True)

            if not success:
                self.log_error(f"Échec de la récupération des détails du tableau RAID '{array_name}': {stderr}")
                return None

            # Parser la sortie
            raid_info = self._parse_mdadm_detail(stdout)
            return raid_info
        else:
            # Vérifier tous les tableaux RAID
            self.log_info("Vérification de tous les tableaux RAID")

            # Obtenir la liste des tableaux
            cmd = ['cat', '/proc/mdstat']
            success, stdout, stderr = self.run(cmd, no_output=True)

            if not success:
                self.log_error(f"Échec de la récupération de l'état des tableaux RAID: {stderr}")
                return []

            # Parser la sortie de /proc/mdstat
            raids = self._parse_mdstat(stdout)

            # Obtenir les détails pour chaque tableau
            for raid in raids:
                detail_cmd = ['mdadm', '--detail', f"/dev/{raid['name']}"]
                detail_success, detail_stdout, _ = self.run_as_root(detail_cmd, no_output=True)

                if detail_success:
                    details = self._parse_mdadm_detail(detail_stdout)
                    raid.update(details)

            return raids

    def repair_raid_array(self, array_name, scan=True, assume_clean=False):
        """
        Tente de réparer un tableau RAID défaillant.

        Args:
            array_name: Nom du tableau RAID à réparer
            scan: Si True, effectue un scan pour détecter les composants
            assume_clean: Si True, suppose que les périphériques sont synchronisés

        Returns:
            bool: True si la réparation a réussi, False sinon
        """
        # Normaliser le nom du tableau
        if not array_name.startswith("/dev/"):
            if not array_name.startswith("md"):
                array_name = f"md{array_name}"
            array_path = f"/dev/{array_name}"
        else:
            array_path = array_name
            array_name = os.path.basename(array_path)

        self.log_warning(f"Tentative de réparation du tableau RAID '{array_name}'")

        # Vérifier l'état actuel
        status = self.check_raid_status(array_name)
        if not status:
            self.log_error(f"Impossible d'obtenir l'état du tableau RAID '{array_name}'")
            return False

        # Si le tableau est déjà en bon état, pas besoin de réparation
        if status.get('state', '').lower() == 'clean' or status.get('state', '').lower() == 'active':
            self.log_info(f"Le tableau RAID '{array_name}' est en bon état, aucune réparation nécessaire")
            return True

        # Si le scan est demandé, tenter de détecter les composants
        if scan:
            self.log_info("Recherche des composants du tableau RAID")
            scan_cmd = ['mdadm', '--scan', '--assemble', array_path]
            scan_success, _, scan_stderr = self.run_as_root(scan_cmd)

            if scan_success:
                self.log_success(f"Tableau RAID '{array_name}' assemblé avec succès")

                # Vérifier l'état après assemblage
                status = self.check_raid_status(array_name)
                if status and (status.get('state', '').lower() == 'clean' or status.get('state', '').lower() == 'active'):
                    return True
            else:
                self.log_warning(f"Échec de l'assemblage automatique: {scan_stderr}")

        # Arrêter le tableau s'il est actif mais dégradé
        stop_cmd = ['mdadm', '--stop', array_path]
        self.run_as_root(stop_cmd)

        # Tenter d'assembler avec --force
        self.log_info("Tentative d'assemblage forcé du tableau RAID")
        assemble_cmd = ['mdadm', '--assemble', '--force', array_path]
        assemble_success, _, assemble_stderr = self.run_as_root(assemble_cmd)

        if not assemble_success:
            self.log_error(f"Échec de l'assemblage forcé: {assemble_stderr}")

            # Dernière tentative: recréer le tableau avec --run
            if 'devices' in status and status['devices']:
                devices = [dev['device'] for dev in status['devices'] if dev['state'] != 'removed']

                if devices:
                    self.log_warning("Tentative de dernière chance: re-création du tableau")

                    # Obtenir le niveau RAID
                    raid_level = status.get('raid_level', '5')  # Niveau 5 par défaut si non trouvé

                    # Recréer le tableau
                    create_cmd = ['mdadm', '--create', '--force', '--run', array_path,
                                 f"--level={raid_level}", f"--raid-devices={len(devices)}"]

                    if assume_clean:
                        create_cmd.append('--assume-clean')

                    create_cmd.extend(devices)

                    create_success, _, create_stderr = self.run_as_root(create_cmd)

                    if create_success:
                        self.log_success(f"Tableau RAID '{array_name}' recréé avec succès")
                        self._update_mdadm_conf()
                        return True
                    else:
                        self.log_error(f"Échec de la re-création du tableau: {create_stderr}")
                        return False
                else:
                    self.log_error("Aucun périphérique valide trouvé pour recréer le tableau")
                    return False
            else:
                self.log_error("Informations insuffisantes sur les périphériques pour tenter une réparation")
                return False
        else:
            self.log_success(f"Tableau RAID '{array_name}' assemblé avec succès")

            # Démarrer la reconstruction si nécessaire
            self.log_info("Vérification de l'état et démarrage de la reconstruction si nécessaire")

            # Forcer une vérification
            check_cmd = ['echo', 'check', '>', f"/sys/block/{array_name}/md/sync_action"]
            self.run_as_root(['bash', '-c', ' '.join(check_cmd)])

            return True

    def rebuild_raid_array(self, array_name, rebuild_device, assume_clean=False):
        """
        Lance la reconstruction d'un périphérique dans un tableau RAID.

        Args:
            array_name: Nom du tableau RAID
            rebuild_device: Périphérique à reconstruire
            assume_clean: Si True, suppose que les données sont synchronisées

        Returns:
            bool: True si le démarrage de la reconstruction a réussi, False sinon
        """
        # Normaliser le nom du tableau
        if not array_name.startswith("/dev/"):
            if not array_name.startswith("md"):
                array_name = f"md{array_name}"
            array_path = f"/dev/{array_name}"
        else:
            array_path = array_name
            array_name = os.path.basename(array_path)

        # Vérifier si le tableau existe
        if not os.path.exists(array_path):
            self.log_error(f"Le tableau RAID '{array_name}' n'existe pas")
            return False

        self.log_info(f"Démarrage de la reconstruction du périphérique '{rebuild_device}' dans le tableau RAID '{array_name}'")

        # Ajouter le périphérique au tableau
        cmd = ['mdadm', '--add', array_path, rebuild_device]

        if assume_clean:
            # Si on suppose que les données sont synchronisées, utiliser la fonction re-add
            cmd = ['mdadm', '--re-add', array_path, rebuild_device]

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Reconstruction du périphérique '{rebuild_device}' démarrée avec succès")

            # Vérifier l'état de la reconstruction
            self._check_raid_rebuild_progress(array_name)

            return True
        else:
            self.log_error(f"Échec du démarrage de la reconstruction: {stderr}")
            return False

    def get_raid_devices(self, array_name):
        """
        Obtient la liste des périphériques d'un tableau RAID.

        Args:
            array_name: Nom du tableau RAID

        Returns:
            list: Liste des périphériques avec leur état
        """
        # Normaliser le nom du tableau
        if not array_name.startswith("/dev/"):
            if not array_name.startswith("md"):
                array_name = f"md{array_name}"
            array_path = f"/dev/{array_name}"
        else:
            array_path = array_name
            array_name = os.path.basename(array_path)

        # Vérifier si le tableau existe
        if not os.path.exists(array_path):
            self.log_error(f"Le tableau RAID '{array_name}' n'existe pas")
            return []

        self.log_info(f"Récupération des périphériques du tableau RAID '{array_name}'")

        # Obtenir les détails du tableau
        status = self.check_raid_status(array_name)
        if not status or 'devices' not in status:
            self.log_error(f"Impossible d'obtenir les informations sur les périphériques du tableau '{array_name}'")
            return []

        return status['devices']

    def grow_raid_array(self, array_name, new_devices=None, new_level=None, new_layout=None):
        """
        Étend ou modifie un tableau RAID existant.

        Args:
            array_name: Nom du tableau RAID
            new_devices: Liste des nouveaux périphériques à ajouter (optionnel)
            new_level: Nouveau niveau RAID (optionnel)
            new_layout: Nouvelle disposition (left-symmetric, etc.) (optionnel)

        Returns:
            bool: True si la modification a réussi, False sinon
        """
        # Normaliser le nom du tableau
        if not array_name.startswith("/dev/"):
            if not array_name.startswith("md"):
                array_name = f"md{array_name}"
            array_path = f"/dev/{array_name}"
        else:
            array_path = array_name
            array_name = os.path.basename(array_path)

        # Vérifier si le tableau existe
        if not os.path.exists(array_path):
            self.log_error(f"Le tableau RAID '{array_name}' n'existe pas")
            return False

        # Obtenir l'état actuel du tableau
        status = self.check_raid_status(array_name)
        if not status:
            self.log_error(f"Impossible d'obtenir l'état du tableau RAID '{array_name}'")
            return False

        # Vérifier si les modifications sont possibles
        current_level = status.get('raid_level')
        if new_level and not self._check_raid_conversion(current_level, new_level):
            self.log_error(f"La conversion du niveau RAID {current_level} vers {new_level} n'est pas supportée")
            return False

        # Ajouter de nouveaux périphériques si spécifiés
        if new_devices:
            self.log_info(f"Ajout de {len(new_devices)} nouveaux périphériques au tableau RAID '{array_name}'")

            # Obtenir le nombre actuel de périphériques
            current_devices = len([d for d in status.get('devices', []) if d['state'] != 'spare'])

            # Ajouter chaque périphérique comme spare
            for device in new_devices:
                add_cmd = ['mdadm', '--add', array_path, device]
                add_success, _, add_stderr = self.run_as_root(add_cmd)

                if not add_success:
                    self.log_error(f"Échec de l'ajout du périphérique '{device}': {add_stderr}")
                    return False

            # Reconfigurer le tableau avec les nouveaux périphériques
            grow_cmd = ['mdadm', '--grow', array_path, f"--raid-devices={current_devices + len(new_devices)}"]
            grow_success, _, grow_stderr = self.run_as_root(grow_cmd)

            if not grow_success:
                self.log_error(f"Échec de la reconfiguration du tableau: {grow_stderr}")
                return False

            self.log_success(f"Tableau RAID '{array_name}' étendu avec {len(new_devices)} nouveaux périphériques")

        # Changer le niveau RAID si spécifié
        if new_level:
            self.log_info(f"Conversion du tableau RAID '{array_name}' du niveau {current_level} vers {new_level}")

            level_cmd = ['mdadm', '--grow', array_path, f"--level={new_level}"]

            if new_layout:
                level_cmd.append(f"--layout={new_layout}")

            level_success, _, level_stderr = self.run_as_root(level_cmd)

            if not level_success:
                self.log_error(f"Échec de la conversion du niveau RAID: {level_stderr}")
                return False

            self.log_success(f"Tableau RAID '{array_name}' converti au niveau {new_level}")

        # Suivre la progression de la reconstruction
        self._check_raid_rebuild_progress(array_name, interval=5, max_checks=5)

        # Mettre à jour mdadm.conf
        self._update_mdadm_conf()

        return True

    def monitor_raid_health(self, email=None, silent=False):
        """
        Vérifie l'état de santé de tous les tableaux RAID et envoie un rapport.

        Args:
            email: Adresse email pour recevoir le rapport (optionnel)
            silent: Si True, n'affiche pas les messages pour les tableaux en bon état

        Returns:
            tuple: (bool, str) - Succès et message de rapport
        """
        self.log_info("Vérification de l'état de santé de tous les tableaux RAID")

        # Vérifier tous les tableaux RAID
        raids = self.check_raid_status()

        if not raids:
            message = "Aucun tableau RAID trouvé sur le système"
            self.log_info(message)
            return True, message

        # Analyser l'état de chaque tableau
        report = []
        has_issues = False

        for raid in raids:
            raid_name = raid.get('name', 'Unknown')
            raid_state = raid.get('state', 'Unknown').lower()

            if raid_state in ['clean', 'active']:
                if not silent:
                    report.append(f"[OK] Tableau RAID {raid_name}: État {raid_state}")
            else:
                has_issues = True
                report.append(f"[ALERTE] Tableau RAID {raid_name}: État {raid_state} - ATTENTION!")

            # Vérifier l'état des périphériques
            if 'devices' in raid:
                for dev in raid['devices']:
                    dev_state = dev.get('state', 'Unknown').lower()
                    dev_name = dev.get('device', 'Unknown')

                    if dev_state not in ['active', 'in_sync']:
                        has_issues = True
                        report.append(f"[ALERTE] Périphérique {dev_name} dans {raid_name}: État {dev_state} - ATTENTION!")
                    elif not silent:
                        report.append(f"[OK] Périphérique {dev_name} dans {raid_name}: État {dev_state}")

        # Résumé
        if has_issues:
            summary = f"ALERTE: Problèmes détectés sur {len(raids)} tableau(x) RAID"
            self.log_warning(summary)
        else:
            summary = f"OK: Tous les {len(raids)} tableau(x) RAID sont en bon état"
            self.log_success(summary)

        report.insert(0, summary)
        report_text = "\n".join(report)

        # Envoyer par email si demandé
        if email and has_issues:
            self.log_info(f"Envoi du rapport d'état RAID à {email}")
            try:
                mail_cmd = ['mail', '-s', f"ALERTE RAID: {summary}", email]
                mail_success, _, _ = self.run(mail_cmd, input_data=report_text)

                if not mail_success:
                    self.log_warning(f"Échec de l'envoi du rapport par email à {email}")
            except Exception as e:
                self.log_warning(f"Erreur lors de l'envoi du rapport par email: {str(e)}")

        return True, report_text

    def configure_raid_monitoring(self, email=None, interval='daily', enable=True):
        """
        Configure une surveillance automatique des tableaux RAID.

        Args:
            email: Adresse email pour recevoir les alertes (optionnel)
            interval: Intervalle entre les vérifications ('hourly', 'daily', 'weekly')
            enable: Si True, active la surveillance, sinon la désactive

        Returns:
            bool: True si la configuration a réussi, False sinon
        """
        self.log_info(f"Configuration de la surveillance RAID ({interval})")

        # Créer un script de vérification
        script_path = "/etc/cron.d/raid_monitor.sh"

        if enable:
            script_content = "#!/bin/bash\n\n"

            # Vérifier l'état des tableaux RAID
            script_content += "# Vérification des tableaux RAID\n"
            script_content += "RAID_STATE=$(cat /proc/mdstat)\n\n"

            # Analyser l'état
            script_content += "# Vérifier les problèmes\n"
            script_content += "if echo \"$RAID_STATE\" | grep -E 'degraded|recovery|resync'; then\n"
            script_content += "  ISSUES=1\n"
            script_content += "  SUBJECT=\"ALERTE: Problème détecté sur les tableaux RAID\"\n"
            script_content += "else\n"
            script_content += "  ISSUES=0\n"
            script_content += "  SUBJECT=\"OK: Tableaux RAID en bon état\"\n"
            script_content += "fi\n\n"

            # Envoyer un rapport par email si spécifié
            if email:
                script_content += f"# Envoyer un rapport par email\n"
                script_content += f"if [ $ISSUES -eq 1 ] || [ \"$1\" = \"--force\" ]; then\n"
                script_content += f"  (echo \"État des tableaux RAID:\" && echo \"\" && cat /proc/mdstat && echo \"\" && echo \"Détails des tableaux:\" && mdadm --detail --scan) | mail -s \"$SUBJECT\" {email}\n"
                script_content += f"fi\n\n"

            # Créer le script de surveillance
            try:
                with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
                    temp_path = temp_file.name
                    temp_file.write(script_content)

                # Déplacer le script vers l'emplacement final
                mv_cmd = ['mv', temp_path, script_path]
                mv_success, _, mv_stderr = self.run_as_root(mv_cmd)

                if not mv_success:
                    self.log_error(f"Échec de la création du script de surveillance: {mv_stderr}")
                    return False

                # Rendre le script exécutable
                chmod_cmd = ['chmod', '+x', script_path]
                self.run_as_root(chmod_cmd)

                # Configurer le cron selon l'intervalle spécifié
                cron_path = ""
                if interval == 'hourly':
                    cron_path = "/etc/cron.hourly/raid_monitor"
                elif interval == 'daily':
                    cron_path = "/etc/cron.daily/raid_monitor"
                elif interval == 'weekly':
                    cron_path = "/etc/cron.weekly/raid_monitor"
                else:
                    self.log_error(f"Intervalle invalide: {interval}")
                    return False

                # Créer le lien symbolique vers le script
                ln_cmd = ['ln', '-sf', script_path, cron_path]
                ln_success, _, ln_stderr = self.run_as_root(ln_cmd)

                if not ln_success:
                    self.log_error(f"Échec de la création du lien cron: {ln_stderr}")
                    return False

                self.log_success(f"Surveillance RAID configurée avec succès (intervalle: {interval})")
                return True

            except Exception as e:
                self.log_error(f"Erreur lors de la configuration de la surveillance RAID: {str(e)}")
                return False
        else:
            # Désactiver la surveillance
            try:
                # Supprimer les liens cron
                for cron_dir in ['hourly', 'daily', 'weekly']:
                    cron_path = f"/etc/cron.{cron_dir}/raid_monitor"
                    if os.path.exists(cron_path):
                        rm_cmd = ['rm', cron_path]
                        self.run_as_root(rm_cmd)

                # Supprimer le script
                if os.path.exists(script_path):
                    rm_cmd = ['rm', script_path]
                    self.run_as_root(rm_cmd)

                self.log_success("Surveillance RAID désactivée avec succès")
                return True

            except Exception as e:
                self.log_error(f"Erreur lors de la désactivation de la surveillance RAID: {str(e)}")
                return False

    def _check_raid_rebuild_progress(self, array_name, interval=5, max_checks=3):
        """
        Vérifie la progression de la reconstruction d'un tableau RAID.

        Args:
            array_name: Nom du tableau RAID
            interval: Intervalle entre les vérifications en secondes
            max_checks: Nombre maximum de vérifications

        Returns:
            None
        """
        # Normaliser le nom du tableau
        if array_name.startswith("/dev/"):
            array_name = os.path.basename(array_name)

        if not array_name.startswith("md"):
            array_name = f"md{array_name}"

        self.log_info(f"Suivi de la progression de la reconstruction du tableau RAID '{array_name}'")

        for i in range(max_checks):
            # Lire l'état de la reconstruction
            cmd = ['cat', '/proc/mdstat']
            success, stdout, _ = self.run(cmd, no_output=True)

            if success:
                # Parse /proc/mdstat pour trouver la progression
                for line in stdout.splitlines():
                    if array_name in line and "recovery" in line:
                        # Exemple: "[=>...................]  recovery = 5.2% (51200/1020160) finish=3.1min speed=5224K/sec"
                        match = re.search(r'recovery = ([0-9.]+)%.*finish=([0-9.]+)(min|sec)', line)
                        if match:
                            percentage = match.group(1)
                            time_left = match.group(2)
                            time_unit = match.group(3)

                            self.log_info(f"Reconstruction en cours: {percentage}% terminé, temps restant: {time_left}{time_unit}")
                            break
                    elif array_name in line and "resync" in line:
                        # Exemple: "[=>...................]  resync = 5.2% (51200/1020160) finish=3.1min speed=5224K/sec"
                        match = re.search(r'resync = ([0-9.]+)%.*finish=([0-9.]+)(min|sec)', line)
                        if match:
                            percentage = match.group(1)
                            time_left = match.group(2)
                            time_unit = match.group(3)

                            self.log_info(f"Resynchronisation en cours: {percentage}% terminé, temps restant: {time_left}{time_unit}")
                            break

            if i < max_checks - 1:
                time.sleep(interval)

        self.log_info(f"La reconstruction du tableau RAID '{array_name}' se poursuit en arrière-plan")

    def _parse_mdstat(self, mdstat_output):
        """
        Parse la sortie de /proc/mdstat pour obtenir des informations sur les tableaux RAID.

        Args:
            mdstat_output: Sortie de /proc/mdstat

        Returns:
            list: Liste des tableaux RAID avec leurs informations
        """
        raids = []
        current_raid = None

        for line in mdstat_output.splitlines():
            line = line.strip()

            # Nouvelle entrée de tableau RAID
            if line.startswith('md'):
                if current_raid:
                    raids.append(current_raid)

                # Extraire le nom et l'état
                parts = line.split(':', 1)
                if len(parts) >= 2:
                    current_raid = {
                        'name': parts[0],
                        'status': parts[1].strip()
                    }

                    # Extraire le niveau RAID et les périphériques
                    match = re.search(r'raid([0-9]+)', line)
                    if match:
                        current_raid['raid_level'] = match.group(1)

                    current_raid['devices'] = []

            # Ligne de périphériques
            elif current_raid and line and not line.startswith('unused'):
                # Exemple: "sda1[0] sdb1[1] sdc1[2]"
                devices = re.findall(r'([a-zA-Z0-9/]+)\[[0-9]+\]', line)
                for device in devices:
                    current_raid['devices'].append({
                        'device': f"/dev/{device}",
                        'state': 'active'  # Par défaut, sera mis à jour avec --detail
                    })

            # Ligne d'état
            elif current_raid and ('recovery' in line or 'resync' in line):
                current_raid['recovery_status'] = line.strip()

        # Ajouter le dernier tableau
        if current_raid:
            raids.append(current_raid)

        return raids

    def _parse_mdadm_detail(self, detail_output):
        """
        Parse la sortie de mdadm --detail pour obtenir des informations détaillées sur un tableau RAID.

        Args:
            detail_output: Sortie de mdadm --detail

        Returns:
            dict: Informations détaillées sur le tableau RAID
        """
        raid_info = {
            'devices': []
        }

        current_section = None

        for line in detail_output.splitlines():
            line = line.strip()

            if not line:
                continue

            # Fin de la section des périphériques
            if current_section == 'devices' and not line.startswith('    '):
                current_section = None

            # Détection de la section des périphériques
            if line.startswith('Number   Major   Minor'):
                current_section = 'devices'
                continue

            # Analyse des périphériques
            if current_section == 'devices' and line.startswith('    '):
                # Exemple: "   0       8        1    active sync   /dev/sda1"
                parts = line.split()
                if len(parts) >= 5:
                    device = {
                        'number': parts[0],
                        'major': parts[1],
                        'minor': parts[2],
                        'state': ' '.join(parts[3:-1]),
                        'device': parts[-1]
                    }
                    raid_info['devices'].append(device)
            else:
                # Autres informations clés (en dehors des périphériques)
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().lower().replace(' ', '_')
                    value = value.strip()

                    # Convertir certaines valeurs
                    if key in ['raid_level']:
                        # Extraire le niveau numérique (RAID-5 -> 5)
                        match = re.search(r'raid([0-9]+)', value.lower())
                        if match:
                            value = match.group(1)

                    raid_info[key] = value

        return raid_info

    def _check_raid_conversion(self, from_level, to_level):
        """
        Vérifie si une conversion de niveau RAID est possible.

        Args:
            from_level: Niveau RAID actuel
            to_level: Niveau RAID cible

        Returns:
            bool: True si la conversion est possible, False sinon
        """
        # Conversions supportées
        # Basé sur les capacités de mdadm (https://raid.wiki.kernel.org/index.php/RAID_Reshaping)
        conversions = {
            '0': ['1', '5', '10'],
            '1': ['0', '5', '10'],
            '4': ['0', '5', '6'],
            '5': ['0', '6'],
            '6': ['5']
        }

        # Normaliser les niveaux (enlever "raid" si présent)
        if str(from_level).lower().startswith('raid'):
            from_level = from_level[4:]

        if str(to_level).lower().startswith('raid'):
            to_level = to_level[4:]

        # Vérifier si la conversion est supportée
        return str(from_level) in conversions and str(to_level) in conversions.get(str(from_level), [])

    def _update_mdadm_conf(self):
        """
        Met à jour le fichier de configuration mdadm.conf avec les tableaux actuels.

        Returns:
            bool: True si la mise à jour a réussi, False sinon
        """
        self.log_info("Mise à jour du fichier mdadm.conf")

        # Sauvegarder le fichier existant
        conf_path = "/etc/mdadm/mdadm.conf"
        if not os.path.exists(os.path.dirname(conf_path)):
            # Chercher d'autres emplacements possibles
            for alt_path in ["/etc/mdadm.conf", "/etc/md.conf"]:
                if os.path.exists(alt_path):
                    conf_path = alt_path
                    break

        if os.path.exists(conf_path):
            backup_path = f"{conf_path}.bak"
            cp_cmd = ['cp', conf_path, backup_path]
            self.run_as_root(cp_cmd)

        # Générer la nouvelle configuration
        scan_cmd = ['mdadm', '--detail', '--scan']
        scan_success, scan_stdout, scan_stderr = self.run_as_root(scan_cmd, no_output=True)

        if not scan_success:
            self.log_error(f"Échec de la génération de la configuration RAID: {scan_stderr}")
            return False

        # Écrire la nouvelle configuration
        conf_content = "# Généré automatiquement par le script de gestion RAID\n"
        conf_content += "# Consultez mdadm.conf(5) pour plus d'informations\n\n"
        conf_content += "DEVICE partitions\n\n"
        conf_content += scan_stdout

        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
                temp_path = temp_file.name
                temp_file.write(conf_content)

            # Déplacer le fichier temporaire vers l'emplacement final
            mv_cmd = ['mv', temp_path, conf_path]
            mv_success, _, mv_stderr = self.run_as_root(mv_cmd)

            if not mv_success:
                self.log_error(f"Échec de la mise à jour de {conf_path}: {mv_stderr}")
                return False

            self.log_success(f"Fichier {conf_path} mis à jour avec succès")
            return True

        except Exception as e:
            self.log_error(f"Erreur lors de la mise à jour de {conf_path}: {str(e)}")
            return False

    def _is_mounted(self, device):
        """
        Vérifie si un périphérique est monté.

        Args:
            device: Chemin du périphérique

        Returns:
            bool: True si le périphérique est monté, False sinon
        """
        cmd = ['mount']
        success, stdout, _ = self.run(cmd, no_output=True)

        if not success:
            return False

        for line in stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0] == device:
                return True

        return False