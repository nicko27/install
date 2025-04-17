# install/plugins/plugins_utils/apt.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module utilitaire pour la gestion complète des paquets Debian/Ubuntu avec apt.
Offre des fonctionnalités avancées pour installer, désinstaller, rechercher et gérer
les paquets et dépôts du système.
"""

# Import de la classe de base et des types
from plugins_utils.plugins_utils_base import PluginsUtilsBase
import os
import re
import time
from pathlib import Path
import shlex
from typing import Union, Optional, List, Dict, Any, Tuple, Set

# Import conditionnel pour ConfigFileCommands (utilisé dans add_repository)
try:
    from .config_files import ConfigFileCommands
    CONFIG_FILES_AVAILABLE = True
except ImportError:
    CONFIG_FILES_AVAILABLE = False
    class ConfigFileCommands: pass # Factice

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
        # Pas de stockage de task_id ici

    def update(self, allow_fail: bool = False) -> bool:
        """
        Met à jour la liste des paquets disponibles via apt-get update.
        Cette méthode gère sa propre barre de progression interne via self.run.

        Args:
            allow_fail: Si True, renvoie True même si des erreurs non critiques surviennent.

        Returns:
            bool: True si la mise à jour a réussi.
        """
        self.log_info("Mise à jour de la liste des paquets (apt update)")
        # Pas de start_task ici

        cmd = ['apt-get', 'update']
        success, stdout, stderr = self.run(cmd,
                                           check=False,
                                           env=self._apt_env,
                                           real_time_output=True, # Active la lecture temps réel
                                           show_progress=True,    # Demande à run de gérer une barre pour cette commande
                                           error_as_warning=allow_fail
                                           )

        # Gérer les erreurs courantes
        warning_issued = False
        final_success = success
        if not success and allow_fail:
            if "NO_PUBKEY" in stderr or "KEYEXPIRED" in stderr:
                self.log_warning("Problèmes de clés GPG détectés, mais continuer quand même.")
                warning_issued = True
                final_success = True
            elif re.search(r'(Failed to fetch|Unable to fetch|Could not resolve)', stderr, re.IGNORECASE):
                self.log_warning("Certains dépôts n'ont pas pu être atteints, mais continuer quand même.")
                warning_issued = True
                final_success = True
        elif not success:
             self.log_error(f"Échec critique de 'apt-get update'. Stderr:\n{stderr}")

        # Log final basé sur le statut
        final_message = "Mise à jour des sources terminée"
        if final_success and not warning_issued:
             final_message += " avec succès."
             self.log_success(final_message)
        elif warning_issued:
             final_message += " avec des avertissements."
             self.log_warning(final_message)
        else: # final_success = False
             final_message += " avec échec critique."
             # l'erreur a déjà été logguée

        # Pas de complete_task ici
        return final_success

    def upgrade(self,
                dist_upgrade: bool = False,
                full_upgrade: bool = False,
                simulate: bool = False,
                autoremove: bool = True) -> bool:
        """
        Met à jour les paquets installés. Ne modifie pas la progression globale.
        Affiche des barres temporaires pour les commandes `apt update`, `apt upgrade` et `apt autoremove`.
        """
        # Pas de gestion de task_id principal ici

        if dist_upgrade:
             upgrade_type_log = "complète (dist-upgrade)"
             cmd_verb = "dist-upgrade"
             apt_cmd = 'apt-get'
        elif full_upgrade:
             upgrade_type_log = "complète (full-upgrade)"
             cmd_verb = "full-upgrade"
             apt_cmd = 'apt'
        else:
             upgrade_type_log = "standard (upgrade)"
             cmd_verb = "upgrade"
             apt_cmd = 'apt-get'

        action_log = "Simulation" if simulate else "Exécution"
        log_prefix = f"{action_log} de la mise à jour {upgrade_type_log}"
        self.log_info(log_prefix)

        # --- Étape 1: Mise à jour des sources ---
        self.log_info(f"{log_prefix} - Étape 1: Mise à jour sources")
        # L'appel à update gère sa propre barre de progression détaillée
        update_success = self.update(allow_fail=True)
        if not update_success:
            self.log_error("Échec critique de la mise à jour des sources. Annulation.")
            return False

        # --- Étape 2: Exécution Upgrade ---
        self.log_info(f"{log_prefix} - Étape 2: Exécution {cmd_verb}")

        cmd = [apt_cmd, cmd_verb]
        cmd.extend(['-o', 'Dpkg::Options::=--force-confdef', '-o', 'Dpkg::Options::=--force-confold'])
        cmd.append('-y')
        if simulate: cmd.append('--simulate')

        # self.run gère la barre de progression temporaire pour cette commande
        upgrade_success, stdout, stderr = self.run(cmd,
                                                   env=self._apt_env,
                                                   check=False,
                                                   timeout=3600,
                                                   real_time_output=True,
                                                   show_progress=True
                                                   )
        if not upgrade_success:
            self.log_error(f"Échec de '{' '.join(cmd)}'. Stderr:\n{stderr}")
            return False # Arrêter ici si l'upgrade échoue

        # --- Étape 3: Autoremove ---
        autoremove_success = True
        if not simulate and autoremove:
            self.log_info(f"{log_prefix} - Étape 3: Nettoyage (autoremove)")
            # L'appel à autoremove gère sa propre barre détaillée
            autoremove_success = self.autoremove(simulate=simulate)
            if not autoremove_success:
                self.log_warning("Échec de l'étape autoremove.")
        else:
            self.log_info(f"{log_prefix} - Terminé (autoremove ignoré)")

        final_success = upgrade_success # Le succès global dépend de l'upgrade
        final_message = f"{log_prefix} {'terminée' if final_success else 'échouée'}"
        if final_success: self.log_success(final_message)
        # Pas de complete_task ici

        return final_success

    def install(self,
                package_names: Union[str, List[str]],
                version: Optional[str] = None,
                reinstall: bool = False,
                auto_fix: bool = True,
                no_recommends: bool = False,
                simulate: bool = False,
                force_conf: bool = True) -> bool:
        """
        Installe un ou plusieurs paquets. Ne modifie pas la progression globale.
        Affiche des barres temporaires pour `apt install` et `apt --fix-broken`.
        """
        # Pas de gestion de task_id principal ici

        if isinstance(package_names, str): packages = [package_names]
        else: packages = list(package_names)
        if not packages:
             self.log_warning("Aucun paquet spécifié pour l'installation.")
             return True

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
             target_packages = packages
        else:
             target_packages = packages

        # --- Étape 1: Tentative d'installation ---
        self.log_info(f"{log_prefix} - Étape 1: Tentative initiale")

        cmd = ['apt-get', 'install', '-y']
        if force_conf: cmd.extend(['-o', 'Dpkg::Options::=--force-confdef', '-o', 'Dpkg::Options::=--force-confold'])
        if reinstall: cmd.append('--reinstall')
        if no_recommends: cmd.append('--no-install-recommends')
        if simulate: cmd.append('--simulate')
        cmd.extend(target_packages)

        # self.run gère la barre de progression temporaire
        install_success, stdout, stderr = self.run(cmd,
                                                   env=self._apt_env,
                                                   check=False,
                                                   real_time_output=True,
                                                   show_progress=True,
                                                   timeout=3600)

        # --- Étape 2: Auto Fix si nécessaire ---
        if not install_success and not simulate and auto_fix:
            if re.search(r'(unmet depend|broken package|held broken)', stderr, re.IGNORECASE):
                self.log_info(f"{log_prefix} - Étape 2: Tentative de réparation")
                self.log_warning("Problème de dépendances détecté, tentative de réparation...")

                # fix_broken gère sa propre barre de progression
                fix_success = self.fix_broken(simulate=simulate)

                if fix_success:
                    self.log_info("Réparation réussie, nouvelle tentative d'installation...")
                    # Nouvelle tentative - self.run gère sa propre barre
                    install_success, stdout, stderr = self.run(cmd,
                                                               env=self._apt_env,
                                                               check=False,
                                                               real_time_output=True,
                                                               show_progress=True,
                                                               timeout=3600)
                else:
                     self.log_error("Échec de la réparation des dépendances.")
                     install_success = False
            else:
                 self.log_info(f"{log_prefix} - Étape 2: Réparation non nécessaire (autre erreur)")
        elif not simulate and auto_fix:
             self.log_info(f"{log_prefix} - Étape 2: Réparation non nécessaire (installation initiale OK)")


        final_message = f"{log_prefix} {'réussie' if install_success else 'échouée'}"

        if not install_success:
            self.log_error(f"Échec final de '{' '.join(cmd)}'.")
            if stderr: self.log_error(f"Dernier Stderr:\n{stderr}")
            if stdout: self.log_info(f"Dernier Stdout:\n{stdout}")
        else:
            self.log_success(final_message)

        # Pas de complete_task ici
        return install_success

    def uninstall(self,
                  package_names: Union[str, List[str]],
                  purge: bool = False,
                  auto_remove: bool = True,
                  simulate: bool = False) -> bool:
        """
        Désinstalle un ou plusieurs paquets. Ne modifie pas la progression globale.
        Affiche des barres temporaires pour `apt remove/purge` et `apt autoremove`.
        """
        # Pas de gestion de task_id principal ici

        if isinstance(package_names, str): packages = [package_names]
        else: packages = list(package_names)
        if not packages:
             self.log_warning("Aucun paquet spécifié pour la désinstallation.")
             return True

        action = "Simulation de désinstallation" if simulate else "Désinstallation"
        action_type = "complète (purge)" if purge else "standard"
        package_str = ", ".join(packages)
        log_prefix = f"{action} {action_type} de {package_str}"
        self.log_info(log_prefix)

        # --- Étape 1: Désinstallation ---
        self.log_info(f"{log_prefix} - Étape 1: Désinstallation")

        cmd = ['apt-get']
        cmd.append('purge' if purge else 'remove')
        cmd.append('-y')
        if simulate: cmd.append('--simulate')
        cmd.extend(packages)

        # self.run gère la barre de progression temporaire
        remove_success, stdout, stderr = self.run(cmd,
                                                  env=self._apt_env,
                                                  check=False,
                                                  real_time_output=True,
                                                  show_progress=True
                                                  )

        if not remove_success:
             self.log_error(f"Échec de '{' '.join(cmd)}'. Stderr:\n{stderr}")
             return False # Arrêter si la désinstallation échoue

        # --- Étape 2: Autoremove ---
        autoremove_success = True
        if not simulate and auto_remove:
            self.log_info(f"{log_prefix} - Étape 2: Nettoyage (autoremove)")
            # autoremove gère sa propre barre
            autoremove_success = self.autoremove(simulate=simulate)
            if not autoremove_success:
                self.log_warning("Échec de l'étape autoremove.")
        else:
            self.log_info(f"{log_prefix} - Terminé (autoremove ignoré)")


        final_success = remove_success # Le succès global dépend de la désinstallation
        final_message = f"{log_prefix} {'terminée' if final_success else 'échouée'}"
        if final_success: self.log_success(final_message)
        # Pas de complete_task ici

        return final_success

    def autoremove(self, purge: bool = False, simulate: bool = False) -> bool:
        """
        Supprime les paquets inutilisés. Gère sa propre barre de progression via self.run.
        """
        cmd = ['apt-get', 'autoremove', '-y']
        if purge: cmd.append('--purge')
        if simulate: cmd.append('--simulate')

        action = "Simulation du nettoyage" if simulate else "Nettoyage"
        log_prefix = f"{action} des paquets inutilisés (autoremove)"
        self.log_info(log_prefix)
        # Pas de start_task ici

        # self.run gère la barre de progression temporaire
        success, stdout, stderr = self.run(cmd,
                                           env=self._apt_env,
                                           check=False,
                                           real_time_output=True,
                                           show_progress=True
                                           )

        final_message = log_prefix
        if success:
            if not simulate:
                if re.search(r'0 upgraded, 0 newly installed, 0 to remove', stdout):
                     final_message += ": Aucun paquet inutile à supprimer."
                     self.log_info(final_message)
                else:
                     final_message += " réussi."
                     self.log_success(final_message)
            else:
                 final_message += " terminé."
                 self.log_info(final_message)
                 self.log_info(f"Simulation stdout:\n{stdout}")
        else:
             final_message += " échoué."
             self.log_error(final_message)
             self.log_error(f"Stderr:\n{stderr}")

        # Pas de complete_task ici
        return success

    def clean(self) -> bool:
        """Nettoie le cache apt."""
        self.log_info("Nettoyage du cache apt (apt-get clean)")
        # Pas de start_task ici
        success, _, stderr = self.run(['apt-get', 'clean'], env=self._apt_env, check=False)
        final_message = "Nettoyage cache apt"
        if success:
             final_message += " réussi."
             self.log_success(final_message)
        else:
             final_message += " échoué."
             self.log_error(f"{final_message}. Stderr:\n{stderr}")
        # Pas de complete_task ici
        return success

    def autoclean(self) -> bool:
        """Nettoie le cache apt des paquets obsolètes."""
        self.log_info("Nettoyage des paquets obsolètes du cache apt (apt-get autoclean)")
        # Pas de start_task ici
        success, _, stderr = self.run(['apt-get', 'autoclean'], env=self._apt_env, check=False)
        final_message = "Nettoyage autoclean cache apt"
        if success:
             final_message += " réussi."
             self.log_success(final_message)
        else:
             final_message += " échoué."
             self.log_error(f"{final_message}. Stderr:\n{stderr}")
        # Pas de complete_task ici
        return success

    def fix_broken(self, simulate: bool = False) -> bool:
        """
        Tente de réparer les dépendances cassées. Gère sa propre barre via self.run.
        """
        cmd = ['apt-get', 'install', '--fix-broken', '-y']
        if simulate: cmd.append('--simulate')

        action = "Simulation de la réparation" if simulate else "Réparation"
        log_prefix = f"{action} des dépendances cassées"
        self.log_info(f"{log_prefix} (apt --fix-broken install)")
        # Pas de start_task ici

        # self.run gère la barre de progression temporaire
        success, stdout, stderr = self.run(cmd,
                                           env=self._apt_env,
                                           check=False,
                                           real_time_output=True,
                                           show_progress=True,
                                           timeout=1800)

        final_message = log_prefix
        if success:
            if not simulate:
                if re.search(r'0 upgraded, 0 newly installed, 0 to remove', stdout) and \
                   re.search(r'0 not upgraded', stdout):
                     final_message += ": Aucune dépendance cassée trouvée."
                     self.log_info(final_message)
                else:
                     final_message += " réussie."
                     self.log_success(final_message)
            else:
                 final_message += " terminée."
                 self.log_info(final_message)
                 self.log_info(f"Simulation stdout:\n{stdout}")
        else:
             final_message += " échouée."
             self.log_error(final_message)
             self.log_error(f"Stderr:\n{stderr}")

        # Pas de complete_task ici
        return success

    def add_repository(self, repo_line: str, key_url: Optional[str] = None, keyring_path: Optional[str] = None) -> bool:
        """
        Ajoute un dépôt APT et sa clé GPG. Gère sa propre progression pour l'étape `apt update`.
        """
        self.log_info(f"Ajout du dépôt: {repo_line}")
        # Pas de gestion de task_id principal ici

        # 1. Gérer la clé GPG
        key_options = ""
        actual_keyring_path = None
        if key_url:
            # ... (logique de gestion de clé inchangée, mais sans update_task/complete_task) ...
            if keyring_path:
                 actual_keyring_path = Path(keyring_path)
                 if not actual_keyring_path.is_absolute():
                      self.log_error(f"Le chemin keyring_path doit être absolu: {keyring_path}")
                      return False # Ne pas continuer
            else:
                try:
                    domain = key_url.split('//')[1].split('/')[0].replace('.', '-')
                    default_keyring_dir = Path("/etc/apt/keyrings")
                    actual_keyring_path = default_keyring_dir / f"{domain}.gpg"
                except IndexError:
                     self.log_error(f"URL de clé invalide fournie: {key_url}")
                     return False # Ne pas continuer

            self.log_info(f"Téléchargement de la clé GPG depuis {key_url} vers {actual_keyring_path}")
            keyring_dir = actual_keyring_path.parent
            if not keyring_dir.exists():
                 self.log_info(f"Création du dossier keyring: {keyring_dir}")
                 mkdir_success, _, mkdir_stderr = self.run(['mkdir', '-p', str(keyring_dir)], check=False, needs_sudo=True)
                 if not mkdir_success:
                      self.log_error(f"Impossible de créer le dossier keyring {keyring_dir}: {mkdir_stderr}")
                      return False # Ne pas continuer

            cmd_curl = ['curl', '-fsSL', key_url]
            success_curl, key_data, stderr_curl = self.run(cmd_curl, check=False, no_output=True)
            if not success_curl:
                 self.log_error(f"Échec du téléchargement de la clé GPG depuis {key_url}. Stderr: {stderr_curl}")
                 return False # Ne pas continuer

            quoted_keyring_path = shlex.quote(str(actual_keyring_path))
            cmd_gpg_tee_str = f"gpg --dearmor --yes -o /dev/stdout | tee {quoted_keyring_path} > /dev/null"
            success_gpg, _, stderr_gpg = self.run(cmd_gpg_tee_str, input_data=key_data, shell=True, check=False, needs_sudo=True)

            if not success_gpg:
                self.log_error(f"Échec du traitement/écriture de la clé GPG vers {actual_keyring_path}. Stderr: {stderr_gpg}")
                self.run(['rm', '-f', str(actual_keyring_path)], check=False, needs_sudo=True)
                return False # Ne pas continuer

            self.run(['chmod', '644', str(actual_keyring_path)], check=False, needs_sudo=True)
            key_options = f"[signed-by={str(actual_keyring_path)}]"
            self.log_success(f"Clé GPG ajoutée avec succès: {actual_keyring_path}")
        else:
            self.log_info("Aucune clé GPG spécifiée pour ce dépôt.")

        # 2. Ajouter la ligne de dépôt
        self.log_info("Configuration du fichier source...")
        # ... (logique extraction nom de fichier inchangée) ...
        repo_parts = repo_line.split()
        repo_name_base = "custom-repo"
        for part in repo_parts:
            if part.startswith(('http://', 'https://')):
                try:
                    repo_name_base = part.split('//')[1].split('/')[0].replace('.', '-').replace(':','-')
                    break
                except IndexError: pass
        arch_part = next((p for p in repo_parts if p.startswith('[') and 'arch=' in p), None)
        if arch_part:
             arch_match = re.search(r'arch=(\S+)', arch_part)
             if arch_match: repo_name_base += f"-{arch_match.group(1).rstrip(']')}"

        source_file_path = Path(f"/etc/apt/sources.list.d/{repo_name_base}.list")

        # ... (logique construction final_repo_line inchangée) ...
        repo_line_parts = repo_line.split(None, 1)
        final_repo_line = repo_line
        if key_options:
            if len(repo_line_parts) == 2 and repo_line_parts[0].startswith("deb"):
                final_repo_line = f"{repo_line_parts[0]} {key_options} {repo_line_parts[1]}"
            else:
                 self.log_warning("Format de ligne de dépôt inconnu, ajout [signed-by] au début.")
                 final_repo_line = f"{key_options} {repo_line}"

        self.log_info(f"Ajout de la ligne au fichier: {source_file_path}")
        if not CONFIG_FILES_AVAILABLE:
             self.log_error("Impossible d'écrire le fichier source: ConfigFileCommands non disponible.")
             return False

        cfg_writer = ConfigFileCommands(self.logger, self.target_ip)
        success_add = cfg_writer._write_file_content(source_file_path, final_repo_line + "\n", backup=True)

        if not success_add:
            self.log_error(f"Échec de l'ajout de la ligne de dépôt à {source_file_path}.")
            return False

        self.log_success(f"Dépôt ajouté avec succès dans {source_file_path}")

        # 3. Mettre à jour les sources
        self.log_info("Mise à jour des sources après ajout du dépôt...")
        # L'appel à self.update gère sa propre barre de progression détaillée
        update_ok = self.update(allow_fail=True)

        final_message = f"Ajout dépôt {repo_name_base} {'terminé' if update_ok else 'terminé avec erreurs update'}"
        # Pas de complete_task ici

        return update_ok

    # --- Méthodes is_installed, get_version, get_candidate_version ---
    # Pas de changement nécessaire ici car elles n'utilisent pas de progression

    def is_installed(self, package_name: str, min_version: Optional[str] = None) -> bool:
        """
        Vérifie si un paquet est installé et éventuellement si la version installée
        est supérieure ou égale à une version minimale.
        """
        self.log_debug(f"Vérification de l'installation du paquet: {package_name}")
        cmd = ['dpkg-query', '--show', '--showformat=${db:Status-Status}', package_name]
        success, stdout, stderr = self.run(cmd, check=False, no_output=True, error_as_warning=True)
        is_installed = success and stdout.strip() == 'installed'
        if not is_installed:
            self.log_debug(f"Paquet '{package_name}' n'est pas installé.")
            return False
        if min_version:
            installed_version = self.get_version(package_name)
            if not installed_version:
                 self.log_warning(f"Paquet '{package_name}' installé mais impossible de récupérer sa version.")
                 return is_installed
            self.log_debug(f"Comparaison version: {installed_version} >= {min_version}")
            cmd_compare = ['dpkg', '--compare-versions', installed_version, 'ge', min_version]
            success_cmp, _, _ = self.run(cmd_compare, check=False, no_output=True, error_as_warning=True)
            if not success_cmp:
                 self.log_warning(f"Paquet '{package_name}' ({installed_version}) ne satisfait pas la version min ({min_version}).")
                 return False
            self.log_info(f"Paquet '{package_name}' ({installed_version}) satisfait la version min ({min_version}).")
        else:
            self.log_info(f"Paquet '{package_name}' est installé.")
        return True

    def get_version(self, package_name: str) -> Optional[str]:
        """Obtient la version installée d'un paquet via `dpkg-query`."""
        self.log_debug(f"Récupération de la version installée de: {package_name}")
        cmd = ['dpkg-query', '--show', '--showformat=${Version}', package_name]
        success, stdout, stderr = self.run(cmd, check=False, no_output=True)
        if success and stdout.strip():
            version = stdout.strip()
            self.log_debug(f"Version installée de {package_name}: {version}")
            return version
        else:
             if not stderr or "no packages found matching" not in stderr.lower():
                self.log_warning(f"Impossible d'obtenir la version de {package_name}. Stderr: {stderr}")
             else:
                self.log_debug(f"Paquet '{package_name}' non trouvé par dpkg-query.")
             return None

    def get_candidate_version(self, package_name: str) -> Optional[str]:
        """Obtient la version candidate via `apt-cache policy`."""
        self.log_debug(f"Récupération de la version candidate de: {package_name}")
        cmd = ['apt-cache', 'policy', package_name]
        success, stdout, stderr = self.run(cmd, check=False, no_output=True)
        if not success:
             if "unable to locate package" in stderr.lower():
                  self.log_warning(f"Paquet '{package_name}' non trouvé dans les sources apt.")
             else:
                  self.log_warning(f"Impossible d'obtenir la policy apt pour {package_name}. Stderr: {stderr}")
             return None
        candidate_version = None
        for line in stdout.splitlines():
            line_strip = line.strip()
            if line_strip.startswith("Candidate:"):
                version_part = line_strip.split(":", 1)[1].strip()
                if version_part != '(none)': candidate_version = version_part
                break
        self.log_debug(f"Version candidate de {package_name}: {candidate_version}")
        return candidate_version