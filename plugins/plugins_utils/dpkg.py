#!/usr/bin/env python3
"""
Module utilitaire pour la gestion avancée des paquets Debian via dpkg.
Permet de gérer les sélections de paquets, les préréponses debconf et les opérations avancées sur dpkg.
"""

from .commands import Commands
import os
import re
import tempfile
import time


class DpkgCommands(Commands):
    """
    Classe avancée pour gérer dpkg, debconf et les sélections de paquets.
    Hérite de la classe Commands pour la gestion des commandes système.
    """

    def __init__(self, logger=None):
        """
        Initialise le gestionnaire dpkg.

        Args:
            logger: Instance de PluginLogger à utiliser
        """
        super().__init__(logger)
        self._package_selections = []
        self._debconf_selections = []

    def add_package_selection(self, package, status="install"):
        """
        Ajoute une sélection de paquet individuelle à la liste cumulative.

        Args:
            package: Nom du paquet
            status: Statut souhaité (install, hold, deinstall, purge)

        Returns:
            bool: True si l'ajout a réussi
        """
        selection = f"{package} {status}"
        self.log_debug(f"Ajout de la sélection de paquet: {selection}")

        # Vérifier si cette sélection existe déjà
        for i, existing in enumerate(self._package_selections):
            if existing.startswith(f"{package} "):
                # Remplacer l'existant
                self._package_selections[i] = selection
                self.log_debug(f"Remplacement de la sélection existante pour {package}")
                return True

        # Ajouter la nouvelle sélection
        self._package_selections.append(selection)
        return True

    def add_package_selections(self, selections, from_file=False):
        """
        Ajoute des sélections de paquets à la liste cumulative.

        Args:
            selections: Chaîne contenant les sélections ou chemin vers un fichier si from_file=True
            from_file: Si True, selections est un chemin vers un fichier de sélections

        Returns:
            bool: True si l'opération a réussi, False sinon
        """
        self.log_info("Ajout de sélections de paquets à la liste cumulative")

        # Charger les sélections
        if from_file:
            if not os.path.exists(selections):
                self.log_error(f"Le fichier de sélections {selections} n'existe pas")
                return False

            self.log_info(f"Chargement des sélections depuis le fichier: {selections}")
            try:
                with open(selections, 'r') as f:
                    selections_text = f.read()
            except Exception as e:
                self.log_error(f"Erreur lors de la lecture du fichier de sélections: {str(e)}")
                return False
        else:
            selections_text = selections

        # Traiter chaque ligne
        lines = selections_text.splitlines()
        count = 0

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split(None, 1)  # Séparer le nom du paquet et son statut
            if len(parts) != 2:
                self.log_warning(f"Format invalide pour la sélection: {line}")
                continue

            package, status = parts
            self.add_package_selection(package, status)
            count += 1

        self.log_info(f"{count} sélections de paquets ajoutées à la liste cumulative")
        return True

    def clear_package_selections(self):
        """
        Efface toutes les sélections de paquets cumulatives.

        Returns:
            bool: True
        """
        self.log_info("Effacement de toutes les sélections de paquets cumulatives")
        self._package_selections = []
        return True

    def apply_package_selections(self):
        """
        Applique toutes les sélections de paquets cumulatives.

        Returns:
            bool: True si l'opération a réussi, False sinon
        """
        if not self._package_selections:
            self.log_warning("Aucune sélection de paquet à appliquer")
            return True

        self.log_info(f"Application de {len(self._package_selections)} sélections de paquets")

        # Créer un fichier temporaire pour les sélections
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_path = temp_file.name
            for selection in self._package_selections:
                temp_file.write(f"{selection}\n")

        # Appliquer les sélections
        try:
            success, stdout, stderr = self.run_as_root(['bash', '-c', f"cat {temp_path} | dpkg --set-selections"])

            if success:
                self.log_success(f"Sélections de paquets appliquées avec succès")
            else:
                self.log_error("Échec de l'application des sélections de paquets")
                if stderr:
                    self.log_error(f"Erreur: {stderr}")

            # Supprimer le fichier temporaire
            os.unlink(temp_path)
            return success

        except Exception as e:
            self.log_error(f"Erreur lors de l'application des sélections: {str(e)}")
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return False

    def get_package_selections(self, package_pattern=None, save_to_file=None):
        """
        Obtient les sélections de paquets actuelles via dpkg-get-selections.

        Args:
            package_pattern: Motif pour filtrer les paquets (optionnel)
            save_to_file: Chemin du fichier où sauvegarder les sélections (optionnel)

        Returns:
            str: Sélections de paquets ou None si erreur
        """
        cmd = ['dpkg', '--get-selections']

        if package_pattern:
            cmd.append(package_pattern)
            self.log_info(f"Récupération des sélections pour les paquets correspondant à: {package_pattern}")
        else:
            self.log_info("Récupération de toutes les sélections de paquets")

        success, stdout, stderr = self.run(cmd, no_output=True)

        if not success:
            self.log_error("Échec de la récupération des sélections de paquets")
            if stderr:
                self.log_error(f"Erreur: {stderr}")
            return None

        # Sauvegarder dans un fichier si demandé
        if save_to_file:
            try:
                with open(save_to_file, "w") as f:
                    f.write(stdout)
                self.log_success(f"Sélections de paquets sauvegardées dans: {save_to_file}")
            except Exception as e:
                self.log_error(f"Échec de la sauvegarde des sélections dans {save_to_file}: {str(e)}")

        selections_count = len(stdout.splitlines())
        self.log_info(f"Récupération de {selections_count} sélections de paquets terminée")
        return stdout

    def add_debconf_selection(self, package, question, type, value):
        """
        Ajoute une préréponse debconf individuelle à la liste cumulative.

        Args:
            package: Nom du paquet
            question: Question debconf
            type: Type de la question (select, string, boolean, etc.)
            value: Valeur à définir

        Returns:
            bool: True si l'ajout a réussi
        """
        selection = f"{package} {question} {type} {value}"
        self.log_debug(f"Ajout de la préréponse debconf: {selection}")

        # Vérifier si cette sélection existe déjà
        for i, existing in enumerate(self._debconf_selections):
            if existing.startswith(f"{package} {question} "):
                # Remplacer l'existante
                self._debconf_selections[i] = selection
                self.log_debug(f"Remplacement de la préréponse existante pour {package} {question}")
                return True

        # Ajouter la nouvelle sélection
        self._debconf_selections.append(selection)
        return True

    def add_debconf_selections(self, selections, from_file=False):
        """
        Ajoute des préréponses debconf à la liste cumulative.

        Args:
            selections: Chaîne contenant les préréponses ou chemin vers un fichier si from_file=True
            from_file: Si True, selections est un chemin vers un fichier de préréponses

        Returns:
            bool: True si l'opération a réussi, False sinon
        """
        self.log_info("Ajout de préréponses debconf à la liste cumulative")

        # Charger les préréponses
        if from_file:
            if not os.path.exists(selections):
                self.log_error(f"Le fichier de préréponses {selections} n'existe pas")
                return False

            self.log_info(f"Chargement des préréponses depuis le fichier: {selections}")
            try:
                with open(selections, 'r') as f:
                    selections_text = f.read()
            except Exception as e:
                self.log_error(f"Erreur lors de la lecture du fichier de préréponses: {str(e)}")
                return False
        else:
            selections_text = selections

        # Traiter chaque ligne
        lines = selections_text.splitlines()
        count = 0

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split(None, 3)  # Diviser en package, question, type, valeur
            if len(parts) != 4:
                self.log_warning(f"Format invalide pour la préréponse debconf: {line}")
                continue

            package, question, type, value = parts
            self.add_debconf_selection(package, question, type, value)
            count += 1

        self.log_info(f"{count} préréponses debconf ajoutées à la liste cumulative")
        return True

    def clear_debconf_selections(self):
        """
        Efface toutes les préréponses debconf cumulatives.

        Returns:
            bool: True
        """
        self.log_info("Effacement de toutes les préréponses debconf cumulatives")
        self._debconf_selections = []
        return True

    def apply_debconf_selections(self):
        """
        Applique toutes les préréponses debconf cumulatives.

        Returns:
            bool: True si l'opération a réussi, False sinon
        """
        if not self._debconf_selections:
            self.log_warning("Aucune préréponse debconf à appliquer")
            return True

        self.log_info(f"Application de {len(self._debconf_selections)} préréponses debconf")

        # Vérifier que debconf-utils est installé
        success, stdout, _ = self.run(['which', 'debconf-set-selections'], no_output=True)
        if not success:
            self.log_warning("Le programme debconf-set-selections n'est pas disponible, tentative d'installation de debconf-utils")
            success, _, _ = self.run_as_root(['apt-get', 'install', '-y', 'debconf-utils'])
            if not success:
                self.log_error("Impossible d'installer debconf-utils, nécessaire pour appliquer les préréponses")
                return False

        # Créer un fichier temporaire pour les préréponses
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_path = temp_file.name
            for selection in self._debconf_selections:
                temp_file.write(f"{selection}\n")

        # Appliquer les préréponses
        try:
            success, stdout, stderr = self.run_as_root(['debconf-set-selections', temp_path])

            if success:
                self.log_success(f"Préréponses debconf appliquées avec succès")
            else:
                self.log_error("Échec de l'application des préréponses debconf")
                if stderr:
                    self.log_error(f"Erreur: {stderr}")

            # Supprimer le fichier temporaire
            os.unlink(temp_path)
            return success

        except Exception as e:
            self.log_error(f"Erreur lors de l'application des préréponses: {str(e)}")
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return False

    def get_debconf_selections(self, package_pattern=None, save_to_file=None):
        """
        Obtient les préréponses debconf actuelles.

        Args:
            package_pattern: Motif pour filtrer les paquets (optionnel)
            save_to_file: Chemin du fichier où sauvegarder les préréponses (optionnel)

        Returns:
            str: Préréponses debconf ou None si erreur
        """
        self.log_info("Récupération des préréponses debconf")

        # Vérifier que debconf-utils est installé
        success, stdout, _ = self.run(['which', 'debconf-get-selections'], no_output=True)
        if not success:
            self.log_warning("Le programme debconf-get-selections n'est pas disponible, tentative d'installation de debconf-utils")
            success, _, _ = self.run_as_root(['apt-get', 'install', '-y', 'debconf-utils'])
            if not success:
                self.log_error("Impossible d'installer debconf-utils, nécessaire pour récupérer les préréponses")
                return None

        if package_pattern:
            # Utiliser grep pour filtrer les résultats
            self.log_info(f"Récupération des préréponses pour les paquets correspondant à: {package_pattern}")
            success, stdout, stderr = self.run(['bash', '-c', f"debconf-get-selections | grep '{package_pattern}'"], no_output=True)
        else:
            self.log_info("Récupération de toutes les préréponses debconf")
            success, stdout, stderr = self.run(['debconf-get-selections'], no_output=True)

        if not success:
            self.log_error("Échec de la récupération des préréponses debconf")
            if stderr:
                self.log_error(f"Erreur: {stderr}")
            return None

        # Sauvegarder dans un fichier si demandé
        if save_to_file:
            try:
                with open(save_to_file, "w") as f:
                    f.write(stdout)
                self.log_success(f"Préréponses debconf sauvegardées dans: {save_to_file}")
            except Exception as e:
                self.log_error(f"Échec de la sauvegarde des préréponses dans {save_to_file}: {str(e)}")

        selections_count = len(stdout.splitlines())
        self.log_info(f"Récupération de {selections_count} préréponses debconf terminée")
        return stdout

    def set_debconf_selection(self, package, question, type, value):
        """
        Définit directement une préréponse debconf individuelle et l'applique immédiatement.

        Args:
            package: Nom du paquet
            question: Question debconf
            type: Type de la question (select, string, boolean, etc.)
            value: Valeur à définir

        Returns:
            bool: True si l'opération a réussi, False sinon
        """
        selection = f"{package} {question} {type} {value}"
        self.log_info(f"Définition de la préréponse debconf: {selection}")

        # Vérifier que debconf-utils est installé
        success, stdout, _ = self.run(['which', 'debconf-set-selections'], no_output=True)
        if not success:
            self.log_warning("Le programme debconf-set-selections n'est pas disponible, tentative d'installation de debconf-utils")
            success, _, _ = self.run_as_root(['apt-get', 'install', '-y', 'debconf-utils'])
            if not success:
                self.log_error("Impossible d'installer debconf-utils, nécessaire pour définir les préréponses")
                return False

        # Créer un fichier temporaire pour la préréponse
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_path = temp_file.name
            temp_file.write(f"{selection}\n")

        # Appliquer la préréponse
        try:
            success, stdout, stderr = self.run_as_root(['debconf-set-selections', temp_path])

            if success:
                self.log_success(f"Préréponse debconf définie avec succès")
            else:
                self.log_error("Échec de la définition de la préréponse debconf")
                if stderr:
                    self.log_error(f"Erreur: {stderr}")

            # Supprimer le fichier temporaire
            os.unlink(temp_path)
            return success

        except Exception as e:
            self.log_error(f"Erreur lors de la définition de la préréponse: {str(e)}")
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return False

    def reconfigure_package(self, package_name, priority="high"):
        """
        Reconfigure un paquet déjà installé.

        Args:
            package_name: Nom du paquet à reconfigurer
            priority: Priorité des questions à poser (low, medium, high, critical)

        Returns:
            bool: True si la reconfiguration a réussi, False sinon
        """
        self.log_info(f"Reconfiguration du paquet {package_name} (priorité: {priority})")

        # Vérifier si le paquet est installé
        success, stdout, _ = self.run(['dpkg', '-s', package_name], no_output=True)
        if not success or "Status: install ok installed" not in stdout:
            self.log_error(f"Le paquet {package_name} n'est pas installé")
            return False

        # Reconfigurer le paquet
        cmd = ['dpkg-reconfigure', f'--priority={priority}']

        # Ajouter l'option non-interactive si des préréponses ont été définies
        if self._debconf_selections:
            cmd.append('--frontend=noninteractive')

        cmd.append(package_name)

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Reconfiguration de {package_name} réussie")
        else:
            self.log_error(f"Échec de la reconfiguration de {package_name}")
            if stderr:
                self.log_error(f"Erreur: {stderr}")

        return success

    def get_package_status(self, package_name):
        """
        Obtient des informations détaillées sur le statut d'un paquet.

        Args:
            package_name: Nom du paquet

        Returns:
            dict: Informations sur le paquet ou None si erreur
        """
        self.log_debug(f"Récupération du statut du paquet {package_name}")
        success, stdout, _ = self.run(['dpkg', '-s', package_name], no_output=True)

        if not success:
            self.log_debug(f"Le paquet {package_name} n'est pas installé")
            return None

        # Parser la sortie
        info = {}
        current_key = None
        multiline_value = []

        for line in stdout.splitlines():
            if not line.strip():
                # Ligne vide, terminer la valeur multiline si nécessaire
                if current_key and multiline_value:
                    info[current_key] = "\n".join(multiline_value)
                    multiline_value = []
                continue

            if line.startswith(" ") and current_key:
                # Continuation d'une valeur multiline
                multiline_value.append(line.strip())
            elif ":" in line:
                # Nouvelle clé
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                current_key = key

                if multiline_value:
                    info[current_key] = "\n".join(multiline_value)
                    multiline_value = []

                info[key] = value

        # Traiter la dernière valeur multiline si nécessaire
        if current_key and multiline_value:
            info[current_key] = "\n".join(multiline_value)

        return info

    def get_package_files(self, package_name):
        """
        Obtient la liste des fichiers installés par un paquet.

        Args:
            package_name: Nom du paquet

        Returns:
            list: Liste des fichiers ou liste vide si le paquet n'est pas installé
        """
        self.log_debug(f"Récupération des fichiers du paquet {package_name}")
        success, stdout, _ = self.run(['dpkg', '-L', package_name], no_output=True)

        if not success:
            self.log_debug(f"Le paquet {package_name} n'est pas installé")
            return []

        files = [line.strip() for line in stdout.splitlines() if line.strip()]
        self.log_debug(f"Le paquet {package_name} contient {len(files)} fichiers")
        return files

    def get_package_config_files(self, package_name):
        """
        Obtient la liste des fichiers de configuration d'un paquet.

        Args:
            package_name: Nom du paquet

        Returns:
            list: Liste des fichiers de configuration ou liste vide si erreur
        """
        self.log_debug(f"Récupération des fichiers de configuration du paquet {package_name}")
        success, stdout, _ = self.run(['dpkg', '-s', package_name], no_output=True)

        if not success:
            self.log_debug(f"Le paquet {package_name} n'est pas installé")
            return []

        config_files = []
        for line in stdout.splitlines():
            if line.startswith("Conffiles:"):
                # Le format est: Conffiles:
                #  /etc/file1 hash1
                #  /etc/file2 hash2
                continue
            elif line.startswith(" "):
                parts = line.strip().split()
                if len(parts) >= 2:
                    config_files.append(parts[0])
            elif config_files:
                # Fin de la section Conffiles
                break

        self.log_debug(f"Le paquet {package_name} contient {len(config_files)} fichiers de configuration")
        return config_files

    def purge_package_config(self, package_name):
        """
        Purge les fichiers de configuration d'un paquet déjà désinstallé.

        Args:
            package_name: Nom du paquet

        Returns:
            bool: True si l'opération a réussi, False sinon
        """
        self.log_info(f"Purge des fichiers de configuration du paquet {package_name}")

        # Vérifier le statut du paquet
        status = self.get_package_status(package_name)

        if status is None:
            self.log_warning(f"Le paquet {package_name} n'est pas installé ou reconnu")
            # Tenter de le purger quand même
            success, stdout, stderr = self.run_as_root(['dpkg', '--purge', package_name])
            return success

        if status.get("Status", "") == "install ok installed":
            self.log_warning(f"Le paquet {package_name} est encore installé, désinstallation et purge")
            success, stdout, stderr = self.run_as_root(['dpkg', '--purge', package_name])
        else:
            self.log_info(f"Purge des fichiers de configuration du paquet {package_name}")
            success, stdout, stderr = self.run_as_root(['dpkg', '--purge', package_name])

        if success:
            self.log_success(f"Purge des fichiers de configuration de {package_name} réussie")
        else:
            self.log_error(f"Échec de la purge des fichiers de configuration de {package_name}")
            if stderr:
                self.log_error(f"Erreur: {stderr}")

        return success

    def force_install_deb(self, deb_file, ignore_deps=False, force_confold=True):
        """
        Installe un fichier .deb avec options avancées, en ignorant les dépendances si demandé.

        Args:
            deb_file: Chemin vers le fichier .deb
            ignore_deps: Si True, ignore les problèmes de dépendances (--force-depends)
            force_confold: Si True, conserve les anciens fichiers de configuration

        Returns:
            bool: True si l'installation a réussi, False sinon
        """
        if not os.path.exists(deb_file):
            self.log_error(f"Le fichier {deb_file} n'existe pas")
            return False

        self.log_info(f"Installation forcée du fichier .deb: {deb_file}")

        # Construire les options dpkg
        cmd = ['dpkg', '--install']

        if ignore_deps:
            cmd.append('--force-depends')

        if force_confold:
            cmd.append('--force-confold')

        cmd.append(deb_file)

        success, stdout, stderr = self.run_as_root(cmd)

        if success:
            self.log_success(f"Installation forcée de {deb_file} réussie")
        else:
            self.log_error(f"Échec de l'installation forcée de {deb_file}")
            if stderr:
                self.log_error(f"Erreur: {stderr}")

        return success

    def dpkg_dselect_upgrade(self):
        """
        Effectue un dselect-upgrade pour appliquer les sélections de paquets.

        Returns:
            bool: True si l'opération a réussi, False sinon
        """
        self.log_info("Exécution de dselect-upgrade pour appliquer les sélections de paquets")

        # Mettre à jour les informations du paquet
        self.log_info("Mise à jour des informations des paquets")
        success, stdout, stderr = self.run_as_root(['apt-get', 'update'])

        if not success:
            self.log_warning("Avertissement lors de la mise à jour des informations des paquets")

        # Exécuter dselect-upgrade
        self.log_info("Exécution de dselect-upgrade")
        success, stdout, stderr = self.run_as_root(['apt-get', 'dselect-upgrade', '-y'])

        if success:
            self.log_success("dselect-upgrade exécuté avec succès")
        else:
            self.log_error("Échec de l'exécution de dselect-upgrade")
            if stderr:
                self.log_error(f"Erreur: {stderr}")

        return success