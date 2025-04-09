# install/plugins/plugins_utils/repair_utils.py
#!/usr/bin/env python3
"""
Module utilitaire pour effectuer des actions de réparation système courantes.
Combine des fonctionnalités d'autres modules utilitaires (apt, dpkg, logs, services).
"""

from plugins_utils.plugins_utils_base import PluginsUtilsBase
import os
import time
from pathlib import Path
from typing import Union, Optional, List, Dict, Any, Tuple

# Importer les autres utilitaires nécessaires de manière sécurisée
try:
    from .apt import AptCommands
    from .dpkg import DpkgCommands
    from .logs import LogCommands
    from .services import ServiceCommands
    from .network import NetworkCommands # Pour redémarrer le réseau
    UTILS_AVAILABLE = True
except ImportError as e:
    UTILS_AVAILABLE = False
    # Définir des classes factices si les imports échouent
    class AptCommands: pass
    class DpkgCommands: pass
    class LogCommands: pass
    class ServiceCommands: pass
    class NetworkCommands: pass
    # Logguer une seule fois l'erreur d'import
    # (Nécessite une initialisation du logger de base ici ou un logger standard)
    import logging
    logging.warning(f"Échec de l'importation d'utilitaires requis pour RepairUtils: {e}. Fonctionnalités limitées.")


class RepairCommands(PluginsUtilsBase):
    """
    Classe pour exécuter des actions de réparation système courantes.
    Hérite de PluginUtilsBase et utilise d'autres commandes utilitaires.
    """

    def __init__(self, logger=None, target_ip=None):
        """Initialise le gestionnaire de réparation."""
        super().__init__(logger, target_ip)
        if not UTILS_AVAILABLE:
            self.log_error("Certains modules utilitaires requis (Apt, Dpkg, Log, Services, Network) sont manquants. "
                           "Les fonctionnalités de réparation seront limitées.")
            self._apt = None
            self._dpkg = None
            self._logs = None
            self._services = None
            self._network = None
        else:
            # Instancier les autres utilitaires
            self._apt = AptCommands(logger, target_ip)
            self._dpkg = DpkgCommands(logger, target_ip)
            self._logs = LogCommands(logger, target_ip)
            self._services = ServiceCommands(logger, target_ip)
            self._network = NetworkCommands(logger, target_ip)

    def apt_fix_broken_install(self) -> bool:
        """
        Tente de réparer les dépendances cassées via 'apt --fix-broken install'.

        Returns:
            bool: True si la réparation a réussi ou si rien n'était cassé.
        """
        if not self._apt:
            self.log_error("Réparation APT impossible: AptCommands non disponible.")
            return False
        self.log_info("Tentative de réparation des dépendances APT cassées...")
        return self._apt.fix_broken()

    def dpkg_configure_pending(self) -> bool:
        """
        Tente de configurer tous les paquets décompressés mais non configurés ('dpkg --configure -a').
        Nécessite root.

        Returns:
            bool: True si la commande s'est exécutée avec succès.
        """
        self.log_info("Tentative de configuration des paquets dpkg en attente (dpkg --configure -a)...")
        # dpkg --configure -a nécessite root
        success, stdout, stderr = self.run(['dpkg', '--configure', '-a'], check=False, needs_sudo=True)
        if stdout: self.log_info(f"Sortie dpkg --configure -a:\n{stdout}") # Peut être verbeux
        if success:
            self.log_success("Configuration des paquets dpkg terminée avec succès.")
            return True
        else:
            self.log_error(f"Échec de 'dpkg --configure -a'. Stderr:\n{stderr}")
            return False

    def force_log_rotation(self, config_file: Optional[str] = None) -> bool:
        """
        Force l'exécution de logrotate pour la configuration globale ou un fichier spécifique.
        Nécessite root.

        Args:
            config_file: Chemin optionnel vers un fichier de configuration logrotate.

        Returns:
            bool: True si succès.
        """
        if not self._logs:
            self.log_error("Rotation des logs impossible: LogCommands non disponible.")
            return False
        return self._logs.force_logrotate(config_file)

    def clear_temp_files(self,
                         directories: Optional[List[str]] = None,
                         older_than_days: int = 7,
                         patterns: Optional[List[str]] = None,
                         dry_run: bool = True) -> bool:
        """
        Nettoie les fichiers temporaires dans des répertoires spécifiés.
        ATTENTION: Utiliser avec prudence. Par défaut en dry_run.

        Args:
            directories: Liste de répertoires à nettoyer (défaut: ['/tmp', '/var/tmp']).
            older_than_days: Supprimer les fichiers plus vieux que N jours (basé sur mtime).
            patterns: Liste de motifs de noms de fichiers à cibler (ex: ['*.tmp', 'sess_*']).
                      Si None, cible tous les fichiers.
            dry_run: Si True (défaut), simule seulement. Si False, supprime réellement.

        Returns:
            bool: True si l'opération (ou simulation) réussit.
        """
        dirs_to_clean = directories or ['/tmp', '/var/tmp']
        patterns_to_use = patterns or ['*'] # Cibler tout par défaut si aucun pattern
        action = "Simulation du nettoyage" if dry_run else "Nettoyage"
        self.log_warning(f"{action} des fichiers temporaires plus vieux que {older_than_days} jours "
                         f"dans {', '.join(dirs_to_clean)} (patterns: {', '.join(patterns_to_use)})")
        if not dry_run:
            self.log_warning("!!! OPÉRATION DE SUPPRESSION RÉELLE ACTIVÉE !!!")

        all_success = True
        # Construire la commande find
        # find /tmp /var/tmp -mindepth 1 \( -name '*.tmp' -o -name 'sess_*' \) -type f -mtime +7 [-print | -delete]
        cmd = ['find'] + dirs_to_clean
        cmd.extend(['-mindepth', '1']) # Ne pas supprimer les dossiers de base eux-mêmes

        # Ajouter les patterns (avec -o pour OR)
        if len(patterns_to_use) == 1 and patterns_to_use[0] != '*':
             cmd.extend(['-name', patterns_to_use[0]])
        elif len(patterns_to_use) > 1:
             cmd.append('\(')
             for i, pattern in enumerate(patterns_to_use):
                  if i > 0: cmd.append('-o')
                  cmd.extend(['-name', pattern])
             cmd.append('\)')

        cmd.extend(['-type', 'f']) # Seulement les fichiers
        cmd.extend(['-mtime', f'+{older_than_days}'])

        if dry_run:
            cmd.append('-print')
        else:
            cmd.extend(['-delete'])

        # find -delete peut nécessiter root pour certains fichiers/dossiers
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)

        if dry_run:
            if success:
                 files_found = stdout.splitlines()
                 if files_found:
                      self.log_info(f"Simulation: {len(files_found)} fichier(s) seraient supprimé(s):")
                      for f in files_found[:10]: self.log_info(f"  - {f}")
                      if len(files_found) > 10: self.log_info("  - ... et autres.")
                 else:
                      self.log_info("Simulation: Aucun fichier temporaire à supprimer trouvé.")
            else:
                 self.log_error(f"Échec de la simulation de nettoyage. Stderr: {stderr}")
                 all_success = False
        else: # Suppression réelle
            if success:
                 self.log_success("Nettoyage des fichiers temporaires terminé avec succès.")
                 # find -delete n'affiche rien en cas de succès
            else:
                 self.log_error(f"Échec du nettoyage des fichiers temporaires. Stderr: {stderr}")
                 all_success = False

        return all_success

    def restart_networking(self, force_network_manager: bool = False) -> bool:
        """
        Tente de redémarrer le service réseau principal.
        ATTENTION: Peut couper la connexion SSH si exécuté à distance !

        Args:
            force_network_manager: Si True, tente de redémarrer NetworkManager même s'il
                                   n'est pas détecté comme gestionnaire principal.

        Returns:
            bool: True si un service réseau a été redémarré avec succès.
        """
        if not self._services:
             self.log_error("Redémarrage réseau impossible: ServiceCommands non disponible.")
             return False

        self.log_warning("Tentative de redémarrage du service réseau principal.")
        self.log_warning("ATTENTION: Cela peut interrompre votre connexion si vous êtes en SSH !")
        time.sleep(3) # Laisser le temps de lire l'avertissement

        restarted = False
        manager = self._network._detect_network_manager() if self._network else None

        # Priorité à NetworkManager s'il est actif ou forcé
        if manager == "NetworkManager" or force_network_manager:
            self.log_info("Tentative de redémarrage de NetworkManager...")
            if self._services.restart("NetworkManager"):
                 self.log_success("Service NetworkManager redémarré.")
                 restarted = True
            else:
                 self.log_error("Échec du redémarrage de NetworkManager.")

        # Essayer systemd-networkd (souvent utilisé par netplan ou seul)
        if not restarted:
            self.log_info("Tentative de redémarrage de systemd-networkd...")
            if self._services.restart("systemd-networkd"):
                 self.log_success("Service systemd-networkd redémarré.")
                 restarted = True
            else:
                 self.log_info("Échec/Pas de redémarrage de systemd-networkd (peut être normal).")

        # Fallback: essayer l'ancien service 'networking' (Debian/Ubuntu)
        if not restarted:
            self.log_info("Tentative de redémarrage du service 'networking' (legacy)...")
            if self._services.restart("networking"):
                 self.log_success("Service 'networking' redémarré.")
                 restarted = True
            else:
                 self.log_info("Échec/Pas de redémarrage de 'networking' (normal sur systèmes récents).")

        if not restarted:
             self.log_error("Aucun service réseau principal n'a pu être redémarré.")
             return False

        return True

    def restart_dns_resolver(self) -> bool:
        """Tente de redémarrer le service de résolution DNS local."""
        if not self._services:
             self.log_error("Redémarrage DNS impossible: ServiceCommands non disponible.")
             return False

        self.log_info("Tentative de redémarrage du service de résolution DNS...")
        restarted = False
        # Essayer systemd-resolved en premier
        if self._services.is_active("systemd-resolved"):
             if self._services.restart("systemd-resolved"):
                  self.log_success("Service systemd-resolved redémarré.")
                  restarted = True
             else:
                  self.log_error("Échec du redémarrage de systemd-resolved.")
        # Ajouter d'autres résolveurs si nécessaire (dnsmasq, bind9 - moins courant localement)
        # elif self._services.is_active("dnsmasq"): ...

        if not restarted:
             self.log_warning("Aucun service de résolution DNS commun (systemd-resolved) actif trouvé ou redémarré.")
             # Retourner True car il n'y avait peut-être rien à faire ? Ou False ? False est plus sûr.
             return False

        return True

