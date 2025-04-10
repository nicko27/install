# install/plugins/plugins_utils/apt.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module utilitaire pour la gestion complète des paquets Debian/Ubuntu avec apt.
Offre des fonctionnalités avancées pour installer, désinstaller, rechercher et gérer
les paquets et dépôts du système avec affichage de la progression.
"""

# Import de la classe de base et des types
from plugins_utils.plugins_utils_base import PluginsUtilsBase
import os
import re
import time
from pathlib import Path
from typing import Union, Optional, List, Dict, Any, Tuple, Set

class AptCommands(PluginsUtilsBase):
    """
    Classe avancée pour gérer les paquets via apt/apt-get.
    Hérite de PluginUtilsBase pour l'exécution de commandes et la progression.
    """

    def __init__(self, logger=None, target_ip=None):
        """
        Initialise le gestionnaire de commandes apt.

        Args:
            logger: Instance de PluginLogger (optionnel).
            target_ip: IP cible pour les logs (optionnel).
        """
        super().__init__(logger, target_ip)
        # Environnement standard pour les commandes apt pour éviter les prompts interactifs
        self._apt_env = os.environ.copy()
        self._apt_env["DEBIAN_FRONTEND"] = "noninteractive"

    def update(self, allow_fail: bool = False, task_id: Optional[str] = None) -> bool:
        """
        Met à jour la liste des paquets disponibles via apt-get update.

        Args:
            allow_fail: Si True, renvoie True même si des erreurs non critiques surviennent
                        (ex: clés GPG manquantes, dépôts indisponibles). Défaut: False.
            task_id: ID de tâche pour la progression (optionnel).

        Returns:
            bool: True si la mise à jour a réussi (ou partiellement réussi si allow_fail=True), False sinon.
        """
        self.log_info("Mise à jour de la liste des paquets (apt update)")
        # Utiliser un ID de tâche unique si non fourni
        current_task_id = task_id or f"apt_update_{int(time.time())}"
        # Démarrer une tâche avec une seule étape pour cette commande
        self.start_task(1, description="Exécution apt update", task_id=current_task_id)

        cmd = ['apt-get', 'update']
        # Exécute sans check=True pour pouvoir analyser stderr en cas d'échec partiel
        # no_output=False pour voir la sortie en temps réel si possible via le logger de base
        success, stdout, stderr = self.run(cmd, check=False, env=self._apt_env, no_output=False, real_time_output=True)
        # Marquer l'étape comme terminée
        self.update_task(description="apt update terminé")

        # Gérer les erreurs courantes comme les clés manquantes ou dépôts indisponibles
        warning_issued = False
        final_success = success # Succès initial de la commande

        if not success:
            # Analyser stderr pour déterminer si l'échec est acceptable avec allow_fail=True
            if allow_fail:
                if "NO_PUBKEY" in stderr or "KEYEXPIRED" in stderr:
                    self.log_warning("Problèmes de clés GPG détectés dans les dépôts, mais continuer quand même.")
                    warning_issued = True
                    final_success = True # Considérer comme un succès partiel
                elif re.search(r'(Failed to fetch|Unable to fetch|Could not resolve)', stderr, re.IGNORECASE):
                    self.log_warning("Certains dépôts n'ont pas pu être atteints, mais continuer quand même.")
                    warning_issued = True
                    final_success = True # Considérer comme un succès partiel

            # Si l'échec n'est pas acceptable ou si allow_fail=False
            if not final_success:
                 self.log_error(f"Échec critique de 'apt-get update'. Stderr:\n{stderr}")

        # Log final basé sur le statut
        if final_success and not warning_issued:
             self.log_success("Mise à jour des sources terminée avec succès.")
        elif warning_issued: # Implique final_success = True
             self.log_warning("Mise à jour des sources terminée avec des avertissements.")

        # Compléter la tâche de progression avec le statut final
        self.complete_task(success=final_success)
        return final_success

    def upgrade(self,
                dist_upgrade: bool = False,
                full_upgrade: bool = False,
                simulate: bool = False,
                autoremove: bool = True,
                task_id: Optional[str] = None) -> bool:
        """
        Met à jour les paquets installés via apt-get upgrade/dist-upgrade ou apt full-upgrade.

        Args:
            dist_upgrade: Si True, utilise `apt-get dist-upgrade` (prioritaire sur full_upgrade).
            full_upgrade: Si True, utilise `apt full-upgrade` (apt).
            simulate: Si True, simule l'opération sans l'effectuer réellement.
            autoremove: Si True (défaut), supprime les paquets inutilisés après la mise à jour.
            task_id: ID de tâche pour la progression (optionnel).

        Returns:
            bool: True si la mise à jour (et l'autoremove si activé) a réussi.
        """
        # Déterminer le type de mise à jour et la commande à utiliser
        if dist_upgrade:
             upgrade_type_log = "complète (dist-upgrade)"
             cmd_verb = "dist-upgrade"
             apt_cmd = 'apt-get'
        elif full_upgrade:
             upgrade_type_log = "complète (full-upgrade)"
             cmd_verb = "full-upgrade"
             apt_cmd = 'apt' # Préférer 'apt' pour full-upgrade
        else:
             upgrade_type_log = "standard (upgrade)"
             cmd_verb = "upgrade"
             apt_cmd = 'apt-get'

        action_log = "Simulation" if simulate else "Exécution"
        log_prefix = f"{action_log} de la mise à jour {upgrade_type_log}"
        self.log_info(log_prefix)

        current_task_id = task_id or f"apt_upgrade_{int(time.time())}"
        # Étapes: 1 (update) + 1 (upgrade) + 1 (autoremove si activé et non simulation)
        total_steps = 2 + (1 if autoremove and not simulate else 0)
        self.start_task(total_steps, description=f"{log_prefix} - Étape 1/ {total_steps}: Mise à jour des sources", task_id=current_task_id)

        # Étape 1: Mise à jour des sources (permettre l'échec partiel)
        update_success = self.update(allow_fail=True)
        if not update_success:
            # Même si allow_fail=True, si update échoue complètement, on arrête
            self.log_error("Échec critique de la mise à jour des sources. Impossible de continuer la mise à jour des paquets.")
            self.complete_task(success=False, message="Échec mise à jour sources")
            return False
        self.update_task(description=f"{log_prefix} - Étape 2/{total_steps}: Exécution {cmd_verb}")

        # Construire la commande upgrade/dist-upgrade/full-upgrade
        cmd = [apt_cmd, cmd_verb]
        # Options pour forcer la configuration par défaut ou ancienne en cas de conflit
        cmd.extend(['-o', 'Dpkg::Options::=--force-confdef', '-o', 'Dpkg::Options::=--force-confold'])
        cmd.append('-y') # Assume yes par défaut en mode non interactif

        if simulate:
             cmd.append('--simulate')

        # Exécuter la commande upgrade
        # Utiliser un timeout long, check=False pour gérer l'autoremove ensuite
        upgrade_success, stdout, stderr = self.run(cmd, env=self._apt_env, check=False, timeout=3600, real_time_output=True)
        self.update_task(description=f"{log_prefix} - {cmd_verb} terminé")

        # Étape 3: Autoremove si succès et demandé
        autoremove_success = True
        if upgrade_success and not simulate and autoremove:
            self.update_task(description=f"{log_prefix} - Étape 3/{total_steps}: Nettoyage (autoremove)")
            autoremove_success = self.autoremove(simulate=simulate) # Passer simulate ici aussi
        elif autoremove and not simulate:
             # Avancer l'étape même si on ne fait pas l'autoremove (car upgrade a échoué)
             self.update_task()

        # Statut final
        final_success = upgrade_success and autoremove_success
        final_message = f"{log_prefix} {'terminée' if final_success else 'échouée'}"
        self.complete_task(success=final_success, message=final_message)

        if not upgrade_success:
            self.log_error(f"Échec de '{' '.join(cmd)}'. Stderr:\n{stderr}")
        if not autoremove_success:
             self.log_warning("Échec de l'étape autoremove.")

        return final_success

    def install(self,
                package_names: Union[str, List[str]],
                version: Optional[str] = None,
                reinstall: bool = False,
                auto_fix: bool = True,
                no_recommends: bool = False,
                simulate: bool = False,
                force_conf: bool = True, # Utiliser -o Dpkg::Options... par défaut
                task_id: Optional[str] = None) -> bool:
        """
        Installe un ou plusieurs paquets avec options avancées et affichage de progression.

        Args:
            package_names: Nom du paquet ou liste de paquets.
            version: Version spécifique à installer (pour un seul paquet).
            reinstall: Réinstaller même si déjà installé (`--reinstall`).
            auto_fix: Tenter `apt --fix-broken install` si des dépendances sont cassées.
            no_recommends: Ne pas installer les paquets recommandés (`--no-install-recommends`).
            simulate: Simuler sans installer (`--simulate`).
            force_conf: Utiliser `-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold`.
                        Défaut: True. Mettre à False pour laisser dpkg demander.
            task_id: ID de tâche pour la progression (optionnel).

        Returns:
            bool: True si l'installation a réussi (et la réparation si tentée).
        """
        if isinstance(package_names, str):
            packages = [package_names]
        else:
            packages = list(package_names) # Assurer que c'est une liste mutable

        if not packages:
             self.log_warning("Aucun paquet spécifié pour l'installation.")
             return True # Ou False selon la sémantique désirée

        action = "Simulation d'installation" if simulate else "Installation"
        package_str = ", ".join(packages)
        log_prefix = f"{action} de: {package_str}"
        self.log_info(log_prefix)

        # Gérer la version spécifique
        target_packages = []
        if version and len(packages) == 1:
             self.log_info(f"Version spécifiée: {version}")
             target_packages.append(f"{packages[0]}={version}")
        elif version:
             self.log_warning("La spécification de version n'est supportée que pour un seul paquet à la fois.")
             target_packages = packages # Installer la version candidate
        else:
             target_packages = packages

        current_task_id = task_id or f"apt_install_{target_packages[0].split('=')[0]}_{int(time.time())}"
        # Estimation grossière: 1 étape par paquet + 1 pour la commande + 1 si auto_fix
        total_steps = len(target_packages) + 1 + (1 if auto_fix else 0)
        self.start_task(total_steps, description=f"{log_prefix} - Étape 1/{total_steps}: Préparation", task_id=current_task_id)

        cmd = ['apt-get', 'install']
        cmd.append('-y') # Assume yes pour le mode non interactif

        # Ajouter les options dpkg pour forcer la configuration si demandé
        if force_conf:
             cmd.extend(['-o', 'Dpkg::Options::=--force-confdef', '-o', 'Dpkg::Options::=--force-confold'])
             self.log_info("Options dpkg: --force-confold, --force-confdef activées.")

        if reinstall: cmd.append('--reinstall')
        if no_recommends: cmd.append('--no-install-recommends')
        if simulate: cmd.append('--simulate')

        cmd.extend(target_packages)

        # Exécuter la commande d'installation
        self.update_task(description=f"{log_prefix} - Étape 2/{total_steps}: Exécution apt-get install")
        # Utiliser check=False pour gérer auto_fix ensuite
        # Utiliser real_time_output pour voir la progression d'apt
        install_success, stdout, stderr = self.run(cmd, env=self._apt_env, check=False, real_time_output=True, timeout=3600)
        # Mettre à jour la progression après la commande principale
        # Avancer d'un nombre d'étapes égal au nombre de paquets traités (estimation)
        self.update_task(advance=len(target_packages), description=f"{log_prefix} - Installation terminée")

        # Gérer auto_fix
        fix_attempted = False
        if not install_success and auto_fix:
            # Vérifier si l'erreur est liée aux dépendances
            if re.search(r'(unmet depend|broken package|held broken)', stderr, re.IGNORECASE):
                self.update_task(description=f"{log_prefix} - Étape 3/{total_steps}: Tentative de réparation")
                fix_attempted = True
                self.log_warning("Problème de dépendances détecté, tentative de réparation avec 'apt --fix-broken install'")
                fix_success = self.fix_broken(simulate=simulate)
                # Pas de mise à jour de la progression ici, fix_broken a sa propre tâche

                if fix_success:
                    self.log_info("Réparation réussie, nouvelle tentative d'installation...")
                    # Nouvelle tentative d'installation
                    self.update_task(description=f"{log_prefix} - Étape 3/{total_steps}: Ré-exécution apt-get install")
                    install_success, stdout, stderr = self.run(cmd, env=self._apt_env, check=False, real_time_output=True, timeout=3600)
                    self.update_task(advance=len(target_packages), description=f"{log_prefix} - Ré-installation terminée")
                else:
                     self.log_error("Échec de la réparation des dépendances.")
                     install_success = False # Confirmer l'échec
            else:
                 # Erreur non liée aux dépendances, avancer l'étape si auto_fix était prévu
                 if auto_fix: self.update_task()
        elif auto_fix:
             # Avancer la dernière étape si auto_fix était prévu mais non nécessaire
             self.update_task()


        final_message = f"{log_prefix} {'réussie' if install_success else 'échouée'}"
        self.complete_task(success=install_success, message=final_message)

        if not install_success:
            self.log_error(f"Échec de '{' '.join(cmd)}'.")
            if stderr: self.log_error(f"Stderr:\n{stderr}")
            # stdout peut aussi contenir des infos utiles sur l'échec
            if stdout: self.log_info(f"Stdout:\n{stdout}")

        return install_success

    def uninstall(self,
                  package_names: Union[str, List[str]],
                  purge: bool = False,
                  auto_remove: bool = True,
                  simulate: bool = False,
                  task_id: Optional[str] = None) -> bool:
        """
        Désinstalle un ou plusieurs paquets.

        Args:
            package_names: Nom du paquet ou liste de paquets.
            purge: Si True, supprime aussi les fichiers de configuration (`purge`).
            auto_remove: Si True (défaut), supprime les dépendances inutilisées après.
            simulate: Simuler sans désinstaller.
            task_id: ID de tâche pour la progression (optionnel).

        Returns:
            bool: True si l'opération a réussi.
        """
        if isinstance(package_names, str):
            packages = [package_names]
        else:
            packages = list(package_names)

        if not packages:
             self.log_warning("Aucun paquet spécifié pour la désinstallation.")
             return True

        action = "Simulation de désinstallation" if simulate else "Désinstallation"
        action_type = "complète (purge)" if purge else "standard"
        package_str = ", ".join(packages)
        log_prefix = f"{action} {action_type} de {package_str}"
        self.log_info(log_prefix)

        current_task_id = task_id or f"apt_remove_{packages[0]}_{int(time.time())}"
        # Étapes: 1 (remove/purge) + 1 (autoremove si activé et non simulation)
        total_steps = 1 + (1 if auto_remove and not simulate else 0)
        self.start_task(total_steps, description=f"{log_prefix} - Étape 1/{total_steps}: Désinstallation", task_id=current_task_id)

        cmd = ['apt-get']
        cmd.append('purge' if purge else 'remove')
        cmd.append('-y') # Assume yes
        if simulate:
             cmd.append('--simulate')
        cmd.extend(packages)

        # Exécuter la commande remove/purge
        remove_success, stdout, stderr = self.run(cmd, env=self._apt_env, check=False, real_time_output=True)
        self.update_task(description=f"{log_prefix} - Désinstallation terminée")

        # Autoremove
        autoremove_success = True
        if remove_success and not simulate and auto_remove:
            self.update_task(description=f"{log_prefix} - Étape 2/{total_steps}: Nettoyage (autoremove)")
            autoremove_success = self.autoremove(simulate=simulate)
        elif auto_remove and not simulate:
             # Avancer l'étape même si remove a échoué
             self.update_task()

        final_success = remove_success and autoremove_success
        final_message = f"{log_prefix} {'terminée' if final_success else 'échouée'}"
        self.complete_task(success=final_success, message=final_message)

        if not remove_success:
            self.log_error(f"Échec de '{' '.join(cmd)}'. Stderr:\n{stderr}")
        if not autoremove_success:
             self.log_warning("Échec de l'étape autoremove.")

        return final_success

    def autoremove(self, purge: bool = False, simulate: bool = False) -> bool:
        """
        Supprime les paquets qui ne sont plus nécessaires via `apt-get autoremove`.

        Args:
            purge: Si True, supprime également les fichiers de configuration (`--purge`).
            simulate: Si True, simule l'opération sans l'effectuer.

        Returns:
            bool: True si l'opération a réussi.
        """
        cmd = ['apt-get', 'autoremove']
        cmd.append('-y')
        if purge:
            cmd.append('--purge')
        if simulate:
            cmd.append('--simulate')

        action = "Simulation du nettoyage" if simulate else "Nettoyage"
        self.log_info(f"{action} des paquets inutilisés (autoremove)")

        success, stdout, stderr = self.run(cmd, env=self._apt_env, check=False, real_time_output=True)

        if success:
            if not simulate:
                # Vérifier si quelque chose a été supprimé
                if re.search(r'0 upgraded, 0 newly installed, 0 to remove', stdout):
                     self.log_info("Aucun paquet inutile à supprimer.")
                else:
                     self.log_success("Paquets inutilisés supprimés avec succès.")
            else:
                 self.log_info("Simulation de nettoyage terminée.")
                 # Afficher ce qui serait supprimé
                 self.log_info(f"Simulation stdout:\n{stdout}")
        else:
             self.log_error(f"Échec du nettoyage des paquets inutilisés. Stderr:\n{stderr}")

        return success

    def clean(self) -> bool:
        """Nettoie le cache apt (`/var/cache/apt/archives`) via `apt-get clean`."""
        self.log_info("Nettoyage du cache apt (apt-get clean)")
        success, _, stderr = self.run(['apt-get', 'clean'], env=self._apt_env, check=False)
        if success:
             self.log_success("Cache apt nettoyé avec succès.")
        else:
             self.log_error(f"Échec du nettoyage du cache apt. Stderr:\n{stderr}")
        return success

    def autoclean(self) -> bool:
        """Nettoie le cache apt des paquets obsolètes via `apt-get autoclean`."""
        self.log_info("Nettoyage des paquets obsolètes du cache apt (apt-get autoclean)")
        success, _, stderr = self.run(['apt-get', 'autoclean'], env=self._apt_env, check=False)
        if success:
             self.log_success("Cache apt (obsolète) nettoyé avec succès.")
        else:
             self.log_error(f"Échec du nettoyage autoclean du cache apt. Stderr:\n{stderr}")
        return success

    def fix_broken(self, simulate: bool = False) -> bool:
        """
        Tente de réparer les dépendances cassées via `apt-get install --fix-broken`.

        Args:
            simulate: Simuler sans réparer.

        Returns:
            bool: True si la réparation a réussi ou si rien n'était cassé.
        """
        cmd = ['apt-get', 'install', '--fix-broken']
        cmd.append('-y')
        if simulate:
            cmd.append('--simulate')

        action = "Simulation de la réparation" if simulate else "Réparation"
        log_prefix = f"{action} des dépendances cassées"
        self.log_info(f"{log_prefix} (apt --fix-broken install)")

        # Utiliser une tâche de progression pour cette opération potentiellement longue
        task_id = f"apt_fix_broken_{int(time.time())}"
        self.start_task(1, description=log_prefix, task_id=task_id)
        success, stdout, stderr = self.run(cmd, env=self._apt_env, check=False, real_time_output=True, timeout=1800)
        self.update_task() # Marquer l'étape comme terminée

        if success:
            if not simulate:
                if re.search(r'0 upgraded, 0 newly installed, 0 to remove', stdout) and \
                   re.search(r'0 not upgraded', stdout):
                     self.log_info("Aucune dépendance cassée à réparer.")
                else:
                     self.log_success("Dépendances cassées réparées avec succès.")
            else:
                 self.log_info("Simulation de réparation terminée.")
                 self.log_info(f"Simulation stdout:\n{stdout}")
            self.complete_task(success=True, message=f"{log_prefix} terminée")
        else:
             self.log_error(f"Échec de la réparation des dépendances cassées. Stderr:\n{stderr}")
             self.complete_task(success=False, message=f"{log_prefix} échouée")

        return success

    def is_installed(self, package_name: str) -> bool:
        """Vérifie si un paquet est installé via `dpkg-query`."""
        self.log_debug(f"Vérification de l'installation du paquet: {package_name}")
        # Utilise dpkg-query pour une vérification fiable de l'état installé
        cmd = ['dpkg-query', '--show', '--showformat=${db:Status-Status}', package_name]
        # Exécute sans check car un paquet non installé donne un code retour non nul
        success, stdout, stderr = self.run(cmd, check=False, no_output=True, error_as_warning=True)

        # dpkg-query retourne 0 et 'installed' si installé
        # retourne 1 et 'unknown' ou 'not-installed' sinon
        is_inst = success and stdout.strip() == 'installed'
        self.log_debug(f"Paquet '{package_name}' est installé: {is_inst}")
        return is_inst

    def get_version(self, package_name: str) -> Optional[str]:
        """Obtient la version installée d'un paquet via `dpkg-query`."""
        self.log_debug(f"Récupération de la version installée de: {package_name}")
        if not self.is_installed(package_name):
            self.log_debug(f"Paquet '{package_name}' non installé.")
            return None

        cmd = ['dpkg-query', '--show', '--showformat=${Version}', package_name]
        success, stdout, stderr = self.run(cmd, check=False, no_output=True)

        if success and stdout.strip():
            version = stdout.strip()
            self.log_debug(f"Version installée de {package_name}: {version}")
            return version
        else:
             # Logguer l'erreur même si is_installed était True (cas étrange)
             self.log_warning(f"Impossible d'obtenir la version de {package_name} (installé). Stderr: {stderr}")
             return None

    def get_candidate_version(self, package_name: str) -> Optional[str]:
        """Obtient la version candidate (disponible à l'installation/màj) via `apt-cache policy`."""
        self.log_debug(f"Récupération de la version candidate de: {package_name}")
        cmd = ['apt-cache', 'policy', package_name]
        success, stdout, stderr = self.run(cmd, check=False, no_output=True)

        if not success:
             # Gérer le cas où le paquet n'existe pas du tout dans les sources
             if "unable to locate package" in stderr.lower():
                  self.log_warning(f"Paquet '{package_name}' non trouvé dans les sources apt.")
             else:
                  self.log_warning(f"Impossible d'obtenir la policy apt pour {package_name}. Stderr: {stderr}")
             return None

        candidate_version = None
        # Format de sortie:
        # Package: ...
        #   Installed: ...
        #   Candidate: ...
        #   Version table:
        #  *** installed_version priority
        #      candidate_version priority
        #         repo_url...
        for line in stdout.splitlines():
            line_strip = line.strip()
            if line_strip.startswith("Candidate:"):
                version_part = line_strip.split(":", 1)[1].strip()
                if version_part != '(none)':
                     candidate_version = version_part
                break # Candidate est généralement l'info pertinente

        self.log_debug(f"Version candidate de {package_name}: {candidate_version}")
        return candidate_version

    def add_repository(self, repo_line: str, key_url: Optional[str] = None, keyring_path: Optional[str] = None) -> bool:
        """
        Ajoute un dépôt APT (ligne dans sources.list.d) et sa clé GPG (via curl | gpg).

        Args:
            repo_line: Ligne du dépôt (ex: "deb [arch=amd64] http://repo... focal main").
                       L'option [signed-by=...] sera ajoutée automatiquement si keyring_path est utilisé.
            key_url: URL de la clé GPG publique à télécharger et ajouter.
            keyring_path: Chemin absolu où enregistrer la clé GPG traitée (ex: /etc/apt/keyrings/mykey.gpg).
                          Si None et key_url est fourni, un chemin par défaut est généré dans /etc/apt/keyrings/.

        Returns:
            bool: True si l'ajout du dépôt et de la clé (si fournie) et la mise à jour des sources ont réussi.
        """
        self.log_info(f"Ajout du dépôt: {repo_line}")
        task_id = f"add_repo_{int(time.time())}"
        # Étapes: 1 (clé GPG) + 1 (fichier source) + 1 (apt update)
        total_steps = 1 + (1 if key_url else 0) + 1
        self.start_task(total_steps, description=f"Ajout dépôt - Étape 1/{total_steps}: Clé GPG", task_id=task_id)

        # 1. Gérer la clé GPG
        key_options = ""
        actual_keyring_path = None
        if key_url:
            if keyring_path:
                 actual_keyring_path = Path(keyring_path)
                 if not actual_keyring_path.is_absolute():
                      self.log_error(f"Le chemin keyring_path doit être absolu: {keyring_path}")
                      self.complete_task(success=False, message="Chemin clé invalide")
                      return False
            else:
                # Générer un chemin par défaut basé sur l'URL
                try:
                    domain = key_url.split('//')[1].split('/')[0].replace('.', '-')
                    default_keyring_dir = Path("/etc/apt/keyrings")
                    actual_keyring_path = default_keyring_dir / f"{domain}.gpg"
                except IndexError:
                     self.log_error(f"URL de clé invalide fournie: {key_url}")
                     self.complete_task(success=False, message="URL Clé invalide")
                     return False

            self.log_info(f"Téléchargement de la clé GPG depuis {key_url} vers {actual_keyring_path}")
            keyring_dir = actual_keyring_path.parent
            # Créer le dossier /etc/apt/keyrings si nécessaire avec sudo
            if not keyring_dir.exists():
                 self.log_info(f"Création du dossier keyring: {keyring_dir}")
                 mkdir_success, _, mkdir_stderr = self.run(['mkdir', '-p', str(keyring_dir)], check=False, needs_sudo=True)
                 if not mkdir_success:
                      self.log_error(f"Impossible de créer le dossier keyring {keyring_dir}: {mkdir_stderr}")
                      self.complete_task(success=False, message="Échec création dossier clé")
                      return False

            # Télécharger la clé avec curl
            cmd_curl = ['curl', '-fsSL', key_url]
            success_curl, key_data, stderr_curl = self.run(cmd_curl, check=False, no_output=True)
            if not success_curl:
                 self.log_error(f"Échec du téléchargement de la clé GPG depuis {key_url}. Stderr: {stderr_curl}")
                 self.complete_task(success=False, message="Échec téléchargement clé")
                 return False

            # Traiter avec gpg --dearmor et écrire dans le fichier avec tee (pour gérer sudo)
            cmd_gpg_tee = ['gpg', '--dearmor', '--yes', '-o', '/dev/stdout', '|', 'tee', str(actual_keyring_path), '>', '/dev/null']
            # Exécuter via shell pour le pipe et tee
            # Passer les données de la clé sur stdin
            success_gpg, _, stderr_gpg = self.run(" ".join(cmd_gpg_tee), input_data=key_data, shell=True, check=False, needs_sudo=True)

            if not success_gpg:
                self.log_error(f"Échec du traitement/écriture de la clé GPG vers {actual_keyring_path}. Stderr: {stderr_gpg}")
                # Nettoyage partiel
                self.run(['rm', '-f', str(actual_keyring_path)], check=False, needs_sudo=True)
                self.complete_task(success=False, message="Échec traitement clé")
                return False

            # Assurer les bonnes permissions sur la clé (644)
            self.run(['chmod', '644', str(actual_keyring_path)], check=False, needs_sudo=True)
            key_options = f"[signed-by={str(actual_keyring_path)}]"
            self.log_success(f"Clé GPG ajoutée avec succès: {actual_keyring_path}")
        else:
            self.log_info("Aucune clé GPG spécifiée pour ce dépôt.")
        self.update_task(description=f"Ajout dépôt - Étape {2 if key_url else 1}/{total_steps}: Fichier source")

        # 2. Ajouter la ligne de dépôt au fichier sources.list.d
        # Extraire les composants pour un nom de fichier plus propre
        repo_parts = repo_line.split()
        repo_name_base = "custom-repo" # Nom par défaut
        for part in repo_parts:
            if part.startswith('http://') or part.startswith('https://'):
                try:
                    repo_name_base = part.split('//')[1].split('/')[0].replace('.', '-').replace(':','-')
                    break
                except IndexError: pass
        # Ajouter l'architecture si présente pour unicité
        arch_part = next((p for p in repo_parts if p.startswith('[') and 'arch=' in p), None)
        if arch_part:
             arch_match = re.search(r'arch=(\S+)', arch_part)
             if arch_match: repo_name_base += f"-{arch_match.group(1).rstrip(']')}"

        source_file_path = Path(f"/etc/apt/sources.list.d/{repo_name_base}.list")

        # Modifier la ligne de dépôt pour inclure les options de clé
        repo_line_parts = repo_line.split(None, 1)
        if len(repo_line_parts) == 2:
            # Insérer les options après 'deb' ou 'deb-src'
            final_repo_line = f"{repo_line_parts[0]} {key_options} {repo_line_parts[1]}"
        else:
             final_repo_line = repo_line # Ne devrait pas arriver

        self.log_info(f"Ajout de la ligne au fichier: {source_file_path}")
        # Écrire le fichier (écrase s'il existe) via _write_file_content
        # Note: _write_file_content gère sudo et backup
        from .config_files import ConfigFileCommands # Import local pour éviter dépendance cyclique stricte
        cfg_writer = ConfigFileCommands(self.logger, self.target_ip)
        success_add = cfg_writer._write_file_content(source_file_path, final_repo_line + "\n", backup=True)

        if not success_add:
            self.log_error(f"Échec de l'ajout de la ligne de dépôt à {source_file_path}.")
            self.complete_task(success=False, message="Échec ajout source")
            return False

        self.log_success(f"Dépôt ajouté avec succès dans {source_file_path}")
        self.update_task(description=f"Ajout dépôt - Étape {total_steps}/{total_steps}: Mise à jour sources")

        # 3. Mettre à jour les sources
        update_ok = self.update(allow_fail=True) # Permettre les erreurs partielles ici

        final_message = f"Ajout dépôt {repo_name_base} {'terminé' if update_ok else 'terminé avec erreurs update'}"
        self.complete_task(success=update_ok, message=final_message)

        return update_ok

