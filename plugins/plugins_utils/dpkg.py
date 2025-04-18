# install/plugins/plugins_utils/dpkg.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module utilitaire pour la gestion avancée des paquets Debian via dpkg.
Permet de gérer les sélections de paquets, les préréponses debconf et les opérations avancées sur dpkg.
"""

# Import de la classe de base et des types
from plugins_utils.plugins_utils_base import PluginsUtilsBase
import os
import re
import tempfile
import time
import shlex
from typing import Union, Optional, List, Dict, Any, Tuple

# Import conditionnel pour AptCommands (utilisé pour installer debconf-utils)
try:
    from .apt import AptCommands
    APT_AVAILABLE_FOR_DPKG = True
except ImportError:
    APT_AVAILABLE_FOR_DPKG = False
    class AptCommands: pass # Factice

class DpkgCommands(PluginsUtilsBase):
    """
    Classe avancée pour gérer dpkg, debconf et les sélections de paquets.
    Hérite de PluginUtilsBase pour l'exécution de commandes et la progression.
    """

    def __init__(self, logger=None, target_ip=None):
        """
        Initialise le gestionnaire de commandes dpkg et debconf.

        Args:
            logger: Instance de PluginLogger (optionnel).
            target_ip: IP cible pour les logs (optionnel).
        """
        super().__init__(logger, target_ip)
        # Stockage interne des sélections en attente
        self._package_selections: Dict[str, str] = {} # {package: status}
        self._debconf_selections: Dict[Tuple[str, str], Tuple[str, str]] = {} # {(pkg, quest): (type, val)}
        # Instance d'AptCommands pour installer debconf-utils si besoin
        self.last_run_return_code = 0
        self._apt_cmd = AptCommands(logger, target_ip) if APT_AVAILABLE_FOR_DPKG else None
        if not APT_AVAILABLE_FOR_DPKG:
             self.log_warning("Module AptCommands non trouvé. L'installation automatique de debconf-utils sera désactivée.")

    def add_package_selection(self, package: str, status: str = "install"):
        """
        Ajoute ou met à jour une sélection de paquet individuelle dans la liste cumulative interne.

        Args:
            package: Nom du paquet.
            status: Statut souhaité ('install', 'hold', 'deinstall', 'purge').
        """
        valid_statuses = ["install", "hold", "deinstall", "purge"]
        status_lower = status.lower()
        if status_lower not in valid_statuses:
             self.log_warning(f"Statut de sélection dpkg invalide '{status}' pour {package}. Utilisation de 'install'.")
             status_lower = "install"
        self.log_debug(f"Ajout/Mise à jour sélection dpkg: {package} -> {status_lower}")
        self._package_selections[package] = status_lower

    def add_package_selections(self, selections: str):
        """
        Ajoute des sélections de paquets depuis une chaîne multiligne à la liste cumulative interne.

        Args:
            selections: Chaîne contenant les sélections (une par ligne: "package status").
        """
        self.log_info("Ajout de sélections de paquets dpkg depuis une chaîne...")
        count = 0
        for line in selections.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split(None, 1) # Split seulement sur le premier espace
            if len(parts) == 2:
                package, status = parts
                self.add_package_selection(package.strip(), status.strip())
                count += 1
            else:
                 self.log_warning(f"Format invalide pour la sélection dpkg ignorée: {line}")
        self.log_info(f"{count} sélections de paquets dpkg ajoutées/mises à jour en mémoire.")

    def load_package_selections_from_file(self, filepath: str) -> bool:
        """Charge les sélections depuis un fichier et les ajoute à la liste cumulative interne."""
        self.log_info(f"Chargement des sélections de paquets dpkg depuis: {filepath}")
        # La lecture du fichier peut nécessiter sudo
        success_read, content, stderr_read = self.run(['cat', filepath], check=False, needs_sudo=True, no_output=True)
        if not success_read:
             if "no such file" in stderr_read.lower():
                  self.log_error(f"Le fichier de sélections dpkg '{filepath}' n'existe pas.")
             else:
                  self.log_error(f"Impossible de lire le fichier de sélections dpkg '{filepath}'. Stderr: {stderr_read}")
             return False
        try:
            self.add_package_selections(content)
            return True
        except Exception as e:
            self.log_error(f"Erreur lors du traitement du contenu du fichier de sélections '{filepath}': {e}")
            return False

    def clear_package_selections(self):
        """Efface toutes les sélections de paquets dpkg en attente (en mémoire)."""
        self.log_info("Effacement des sélections de paquets dpkg en attente.")
        self._package_selections = {}

    def apply_package_selections(self, task_id: Optional[str] = None) -> bool:
        """
        Applique toutes les sélections de paquets en attente via `dpkg --set-selections`.
        La liste interne est vidée après une application réussie.

        Args:
            task_id: ID de tâche pour la progression (optionnel).

        Returns:
            bool: True si l'opération a réussi.
        """
        if not self._package_selections:
            self.log_warning("Aucune sélection de paquet dpkg en attente à appliquer.")
            return True

        count = len(self._package_selections)
        self.log_info(f"Application de {count} sélections de paquets dpkg...")
        current_task_id = task_id or f"dpkg_set_selections_{int(time.time())}"
        self.start_task(1, description="Application via dpkg --set-selections", task_id=current_task_id)

        # Construire la chaîne pour stdin
        selections_str = "\n".join(f"{pkg}\t{status}" for pkg, status in self._package_selections.items()) + "\n"
        self.log_debug(f"Contenu envoyé à dpkg --set-selections:\n{selections_str}")

        # Appeler dpkg --set-selections via stdin
        cmd = ['dpkg', '--set-selections']
        success, stdout, stderr = self.run(cmd, input_data=selections_str, check=False, needs_sudo=True)
        self.update_task() # Termine l'étape

        if success:
             self.log_success(f"{count} sélections de paquets dpkg appliquées avec succès.")
             self.clear_package_selections() # Vider après succès
             self.complete_task(success=True)
             return True
        else:
             self.log_error("Échec de l'application des sélections de paquets dpkg.")
             if stderr: self.log_error(f"Stderr: {stderr}")
             if stdout: self.log_info(f"Stdout: {stdout}") # stdout peut contenir des infos utiles
             self.complete_task(success=False, message="Échec dpkg --set-selections")
             return False

    # --- Méthodes Debconf ---

    def _ensure_debconf_utils(self) -> bool:
        """Vérifie si debconf-utils est installé, et tente de l'installer sinon."""
        # Vérifier si la commande debconf-set-selections existe
        success_which, _, _ = self.run(['which', 'debconf-set-selections'], check=False, no_output=True, error_as_warning=True)
        if success_which:
            return True

        self.log_warning("Le paquet 'debconf-utils' semble manquant...")
        if not self._apt_cmd:
             self.log_error("Impossible de tenter l'installation de 'debconf-utils' car AptCommands n'est pas disponible.")
             return False

        self.log_info("Tentative d'installation de 'debconf-utils' via AptCommands...")
        # Utiliser l'instance AptCommands pour l'installation
        install_success = self._apt_cmd.install('debconf-utils', auto_fix=True)
        if not install_success:
            self.log_error("Impossible d'installer 'debconf-utils', les opérations debconf échoueront.")
            return False
        self.log_info("'debconf-utils' installé avec succès.")
        # Re-vérifier la commande après installation
        recheck_success, _, _ = self.run(['which', 'debconf-set-selections'], check=False, no_output=True, error_as_warning=True)
        return recheck_success

    def add_debconf_selection(self, package: str, question: str, q_type: str, value: str):
        """
        Ajoute ou met à jour une pré-réponse debconf individuelle dans la liste cumulative interne.

        Args:
            package: Nom du paquet.
            question: Nom de la question debconf (ex: 'shared/accepted-oracle-license-v1-1').
            q_type: Type de la question (string, boolean, select, password, note, text, etc.).
            value: Valeur de la réponse (ex: 'true', 'password', 'Yes').
        """
        key = (package, question)
        # Nettoyer les arguments
        pkg_clean = package.strip()
        quest_clean = question.strip()
        type_clean = q_type.strip()
        val_clean = value.strip() # Ne pas convertir en booléen ici, garder la chaîne

        self.log_debug(f"Ajout/Mise à jour debconf: {pkg_clean} {quest_clean} {type_clean} '{val_clean}'")
        self._debconf_selections[(pkg_clean, quest_clean)] = (type_clean, val_clean)

    def add_debconf_selections(self, selections: str):
        """Ajoute des pré-réponses debconf depuis une chaîne multiligne à la liste cumulative interne."""
        self.log_info("Ajout de pré-réponses debconf depuis une chaîne...")
        count = 0
        for line in selections.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Format: package question type value (séparés par espaces)
            parts = line.split(None, 3) # Split max 3 fois pour garder la valeur entière
            if len(parts) == 4:
                pkg, quest, q_type, val = parts
                self.add_debconf_selection(pkg, quest, q_type, val)
                count += 1
            else:
                 self.log_warning(f"Format invalide pour la pré-réponse debconf ignorée: {line}")
        self.log_info(f"{count} pré-réponses debconf ajoutées/mises à jour en mémoire.")

    def load_debconf_selections_from_file(self, filepath: str) -> bool:
        """Charge les pré-réponses debconf depuis un fichier et les ajoute à la liste interne."""
        self.log_info(f"Chargement des pré-réponses debconf depuis: {filepath}")
        # Vérifier debconf-utils avant de lire

        # Lire le fichier (peut nécessiter sudo)
        success_read, content, stderr_read = self.run(['cat', filepath], check=False, needs_sudo=True, no_output=True)
        if not success_read:
             if "no such file" in stderr_read.lower():
                  self.log_error(f"Le fichier de pré-réponses debconf '{filepath}' n'existe pas.")
             else:
                  self.log_error(f"Impossible de lire le fichier de pré-réponses debconf '{filepath}'. Stderr: {stderr_read}")
             return False
        try:
            self.add_debconf_selections(content)
            return True
        except Exception as e:
            self.log_error(f"Erreur lors du traitement du contenu du fichier debconf '{filepath}': {e}")
            return False

    def clear_debconf_selections(self):
        """Efface toutes les pré-réponses debconf en attente (en mémoire)."""
        self.log_info("Effacement des pré-réponses debconf en attente.")
        self._debconf_selections = {}

    def apply_debconf_selections(self, task_id: Optional[str] = None) -> bool:
        """
        Applique toutes les pré-réponses debconf en attente via `debconf-set-selections`.
        La liste interne est vidée après une application réussie.

        Args:
            task_id: ID de tâche pour la progression (optionnel).

        Returns:
            bool: True si l'opération a réussi.
        """
        if not self._debconf_selections:
            self.log_warning("Aucune pré-réponse debconf en attente à appliquer.")
            return True

        count = len(self._debconf_selections)
        self.log_info(f"Application de {count} pré-réponses debconf...")
        current_task_id = task_id or f"debconf_set_selections_{int(time.time())}"
        self.start_task(1, description="Application via debconf-set-selections", task_id=current_task_id)

        # Construire la chaîne pour stdin
        selections_str = ""
        for (pkg, quest), (q_type, value) in self._debconf_selections.items():
             # Format: package question type value
             selections_str += f"{pkg} {quest} {q_type} {value}\n"
        self.log_debug(f"Contenu envoyé à debconf-set-selections:\n{selections_str}")

        # Appeler debconf-set-selections via stdin
        cmd = ['debconf-set-selections']
        success, stdout, stderr = self.run(cmd, input_data=selections_str, check=False, needs_sudo=True)
        self.update_task() # Termine l'étape

        if success:
             self.log_success(f"{count} pré-réponses debconf appliquées avec succès.")
             self.clear_debconf_selections() # Vider après succès
             self.complete_task(success=True)
             return True
        else:
             self.log_error("Échec de l'application des pré-réponses debconf.")
             if stderr: self.log_error(f"Stderr: {stderr}")
             if stdout: self.log_info(f"Stdout: {stdout}")
             self.complete_task(success=False, message="Échec debconf-set-selections")
             return False

    def get_debconf_selections_for_package(self, package_name: str) -> Optional[Dict[Tuple[str, str], str]]:
        """
        Récupère les sélections debconf actuelles pour un paquet spécifique.

        Args:
            package_name: Nom du paquet.

        Returns:
            Dictionnaire où la clé est un tuple (question, type) et la valeur est la sélection actuelle.
            Retourne None en cas d'erreur, ou un dictionnaire vide si aucune sélection trouvée.
        """
        self.log_debug(f"Récupération des sélections debconf pour le paquet: {package_name}")

        # Construire la commande: debconf-get-selections | grep '^paquet '
        # Utiliser shlex.quote pour sécuriser le nom du paquet dans la commande shell
        cmd_str = f"debconf-get-selections | grep '^{shlex.quote(package_name)}\\s'"
        # Exécuter avec shell=True. check=False car grep retourne 1 si rien n'est trouvé.
        # Pas besoin de sudo pour debconf-get-selections
        success, stdout, stderr = self.run(cmd_str, shell=True, check=False, no_output=True, needs_sudo=False)

        selections: Dict[Tuple[str, str], str] = {}

        if not success:
            # Vérifier si l'échec est dû au fait que grep n'a rien trouvé (code retour 1)
            if self.last_run_return_code and self.last_run_return_code == 1:
                self.log_debug(f"Aucune sélection debconf trouvée pour le paquet '{package_name}'.")
                return selections # Retourner un dict vide
            else:
                # Autre erreur
                self.log_error(f"Échec de la récupération des sélections debconf pour '{package_name}'. Stderr: {stderr}")
                return None

        # Parser la sortie
        count = 0
        for line in stdout.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Format: package question type value
            parts = line.split(None, 3)
            if len(parts) == 4:
                pkg, quest, q_type, val = parts
                # Double vérification que le paquet est correct (même si grep devrait l'assurer)
                if pkg == package_name:
                    selections[(quest, q_type)] = val
                    count += 1
                else:
                    self.log_warning(f"Ligne inattendue retournée par grep: {line}")
            else:
                self.log_warning(f"Format de sélection debconf invalide ignoré: {line}")

        self.log_debug(f"{count} sélection(s) debconf trouvée(s) pour '{package_name}'.")
        self.log_debug(f"Sélections pour {package_name}: {selections}")
        return selections

    def get_debconf_value(self, package_name: str, question_name: str) -> Optional[str]:
        """
        Récupère la valeur d'une question debconf spécifique pour un paquet donné.

        Args:
            package_name: Nom du paquet.
            question_name: Nom de la question debconf.

        Returns:
            La valeur de la sélection sous forme de chaîne, ou None si non trouvée ou en cas d'erreur.
        """
        self.log_debug(f"Recherche de la valeur debconf pour: {package_name} -> {question_name}")
        package_selections = self.get_debconf_selections_for_package(package_name)

        if package_selections is None:
            self.log_error(f"Impossible de récupérer les sélections pour {package_name} afin d'obtenir la valeur.")
            return None

        # Chercher la question dans les sélections récupérées
        for (question, q_type), value in package_selections.items():
            if question == question_name:
                self.log_debug(f"Valeur trouvée pour '{question_name}' ({package_name}): '{value}' (type: {q_type})")
                return value

        self.log_debug(f"Aucune valeur debconf trouvée pour la question '{question_name}' du paquet '{package_name}'.")
        return None
