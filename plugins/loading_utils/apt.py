#!/usr/bin/env python3
"""
Module utilitaire pour la gestion complète des paquets Debian/Ubuntu avec apt.
Offre des fonctionnalités avancées pour installer, désinstaller, rechercher et gérer
les paquets et dépôts du système avec affichage de la progression.
"""

from .commands import Commands
import os
import re
import time


class AptCommands(Commands):
    """
    Classe avancée pour gérer les paquets via apt/apt-get/dpkg.
    Hérite de la classe Commands pour la gestion des commandes système.
    """

    def update(self, allow_fail=False):
        """
        Met à jour la liste des paquets disponibles via apt-get update.

        Args:
            allow_fail: Si True, renvoie True même si des erreurs non critiques surviennent

        Returns:
            bool: True si la mise à jour a réussi, False sinon
        """
        self.log_info("Mise à jour de la liste des paquets")
        self.set_total_steps(1)
        self.next_step("Exécution de apt-get update")

        success, _, stderr = self.run_as_root(['apt-get', 'update'])

        # Gérer les erreurs courantes comme les clés manquantes
        if not success and allow_fail:
            if "NO_PUBKEY" in stderr or "KEYEXPIRED" in stderr:
                self.log_warning("Problèmes de clés détectés dans les dépôts, mais continuer quand même")
                return True

            if "Some index files failed to download" in stderr:
                self.log_warning("Certains fichiers d'index n'ont pas pu être téléchargés, mais continuer quand même")
                return True

        if success:
            self.log_success("Mise à jour des sources terminée avec succès")
        else:
            self.log_error("Échec de la mise à jour des sources")

        return success

    def upgrade(self, dist_upgrade=False, full_upgrade=False, only_security=False, simulate=False, autoremove=True):
        """
        Met à jour les paquets installés via apt-get upgrade avec options avancées.

        Args:
            dist_upgrade: Si True, utilise dist-upgrade (prioritaire sur full_upgrade)
            full_upgrade: Si True, utilise full-upgrade (apt)
            only_security: Si True, met à jour uniquement les paquets de sécurité
            simulate: Si True, simule l'opération sans l'effectuer réellement
            autoremove: Si True, supprime les paquets inutilisés après la mise à jour

        Returns:
            bool: True si la mise à jour a réussi, False sinon
        """
        # Détermine le type de mise à jour
        if dist_upgrade:
            upgrade_type = "complète (dist-upgrade)"
            cmd_type = "dist-upgrade"
        elif full_upgrade:
            upgrade_type = "complète (full-upgrade)"
            cmd_type = "full-upgrade"
        else:
            upgrade_type = "standard"
            cmd_type = "upgrade"

        # Simulation ou exécution
        action = "Simulation" if simulate else "Exécution"

        # Définir les étapes
        steps = 3  # mise à jour sources + analyse + mise à jour
        if autoremove and not simulate:
            steps += 1
        self.set_total_steps(steps)

        # Étape 1: Mise à jour des sources
        self.next_step(f"Mise à jour des sources apt")
        update_success = self.update(allow_fail=True)
        if not update_success:
            self.log_warning("Des erreurs sont survenues lors de la mise à jour des sources")

        # Étape 2: Analyse des paquets à mettre à jour
        self.next_step(f"Analyse des paquets à mettre à jour")
        cmd = ['apt-get']

        if cmd_type == "full-upgrade":
            cmd[0] = 'apt'  # apt full-upgrade au lieu de apt-get

        cmd.append(cmd_type)

        # Ajouter les options
        if simulate:
            cmd.append('--simulate')
        else:
            cmd.append('-y')

        # Mise à jour sécurité uniquement
        temp_security_file = None
        if only_security:
            # Créer un fichier de liste de sources temporaire
            temp_security_file = "/tmp/security-sources.list"
            with open(temp_security_file, "w") as f:
                f.write("# Sources de sécurité uniquement\n")

                # Lire les sources actuelles et filtrer celles de sécurité
                success, stdout, _ = self.run(['cat', '/etc/apt/sources.list'], no_output=True)
                if success:
                    for line in stdout.splitlines():
                        if "security" in line and not line.strip().startswith("#"):
                            f.write(line + "\n")

                # Vérifier aussi dans sources.list.d
                if os.path.exists("/etc/apt/sources.list.d"):
                    for file in os.listdir("/etc/apt/sources.list.d"):
                        if file.endswith(".list"):
                            success, stdout, _ = self.run(['cat', f'/etc/apt/sources.list.d/{file}'], no_output=True)
                            if success:
                                for line in stdout.splitlines():
                                    if "security" in line and not line.strip().startswith("#"):
                                        f.write(line + "\n")

            # Ajouter l'option pour utiliser la liste temporaire
            cmd.extend(['-o', f'Dir::Etc::SourceList={temp_security_file}'])
            upgrade_type += " (sécurité uniquement)"

        # Étape 3: Exécution de la mise à jour
        self.next_step(f"{action} de la mise à jour {upgrade_type}")
        self.log_info(f"Mise à jour {upgrade_type} des paquets")
        success, stdout, stderr = self.run_as_root(cmd)

        # Supprimer le fichier temporaire si créé
        if only_security and temp_security_file and os.path.exists(temp_security_file):
            os.remove(temp_security_file)

        # Si succès et pas en mode simulation, exécuter autoremove si demandé
        if success and not simulate and autoremove:
            self.next_step("Suppression des paquets inutilisés")
            self.autoremove()

        if success:
            if not simulate:
                self.log_success(f"Mise à jour {upgrade_type} terminée avec succès")
            else:
                self.log_info(f"Simulation de mise à jour {upgrade_type} terminée")
        else:
            self.log_error(f"Échec de la mise à jour {upgrade_type}")

        return success

    def install(self, package_names, version=None, reinstall=False, auto_fix=True, from_file=False,
                no_recommends=False, no_suggests=False, assume_yes=True, assume_no=False,
                force_confold=False, force_confdef=False, simulate=False, force=False):
        """
        Installe un ou plusieurs paquets avec options avancées et affichage de progression.

        Args:
            package_names: Nom du paquet ou liste de paquets à installer
            version: Version spécifique à installer
            reinstall: Réinstaller le paquet même s'il est déjà installé
            auto_fix: Tenter de réparer les dépendances cassées si nécessaire
            from_file: Si True, package_names est un chemin vers un fichier de paquets
            no_recommends: Ne pas installer les paquets recommandés
            no_suggests: Ne pas installer les paquets suggérés
            assume_yes: Répondre oui automatiquement aux questions
            assume_no: Répondre non automatiquement aux questions (prioritaire sur assume_yes)
            force_confold: Conserver l'ancienne version des fichiers de configuration
            force_confdef: Utiliser les valeurs par défaut des fichiers de configuration
            simulate: Simuler l'installation sans l'effectuer
            force: Forcer l'installation même en cas de problèmes

        Returns:
            bool: True si l'installation a réussi, False sinon
        """
        # Convertir en liste si nécessaire
        if isinstance(package_names, list):
            packages = package_names
        elif from_file:
            # Pour une installation depuis un fichier, nous ne connaissons pas le nombre
            # exact de paquets à l'avance
            packages = ["(multiples paquets depuis fichier)"]
        else:
            packages = [package_names]

        # Déterminer le mode d'opération
        action = "Simulation de l'installation" if simulate else "Installation"

        # Afficher clairement ce que nous allons installer
        package_str = ", ".join(packages)
        self.log_info(f"{action} de: {package_str}")
        if version:
            self.log_info(f"Version spécifiée: {version}")
        if reinstall:
            self.log_info("Mode: Réinstallation forcée")

        # Options
        options_list = []
        if no_recommends:
            options_list.append("Sans paquets recommandés")
        if no_suggests:
            options_list.append("Sans paquets suggérés")
        if force:
            options_list.append("Installation forcée (downgrades/changements critiques)")
        if assume_yes and not assume_no:
            options_list.append("Confirmation automatique (yes)")
        if assume_no:
            options_list.append("Rejet automatique (no)")
        if force_confold:
            options_list.append("Conserver les anciens fichiers de configuration")
        if force_confdef:
            options_list.append("Utiliser les valeurs par défaut des fichiers de configuration")

        if options_list:
            self.log_info(f"Options: {', '.join(options_list)}")

        # Construire la commande d'installation avec les options
        self.log_info("Préparation de la commande d'installation...")

        # Options de l'environnement pour dpkg (fichiers de configuration)
        env_options = {}
        dpkg_options = []

        if force_confold:
            dpkg_options.append("confold")
        if force_confdef:
            dpkg_options.append("confdef")

        if dpkg_options:
            env_options["DEBIAN_FRONTEND"] = "noninteractive"
            env_option_str = " ".join([f"--force-{opt}" for opt in dpkg_options])
            env_options["DPKG_OPTIONS"] = f"--force-confdef --force-confold"
            self.log_info(f"Options dpkg: {env_option_str}")

        # Début de la commande apt-get
        cmd = ['apt-get']

        # Ajout des options environnement si nécessaires
        if env_options:
            # Nous devrons utiliser un wrapper bash pour passer les variables d'environnement
            env_prefix = []
            for key, value in env_options.items():
                env_prefix.append(f"{key}='{value}'")

        # Options apt-get
        if reinstall:
            cmd.append('--reinstall')

        if no_recommends:
            cmd.append('--no-install-recommends')

        if no_suggests:
            cmd.append('--no-install-suggests')

        if simulate:
            cmd.append('--simulate')
        elif assume_yes and not assume_no:
            cmd.append('-y')
        elif assume_no:
            cmd.append('--assume-no')

        if force:
            cmd.extend(['--allow-downgrades', '--allow-remove-essential', '--allow-change-held-packages'])

        cmd.append('install')

        # Afficher la progression en pourcentage approximatif
        total_steps = 5
        current_step = 0

        # Étape 1: Initialisation
        current_step += 1
        progress = int(current_step / total_steps * 100)
        self.log_info(f"[Progression: {progress}%] Préparation de l'installation...")

        # Gérer les paquets
        if from_file:
            # Installer depuis un fichier
            if not os.path.exists(package_names):
                self.log_error(f"Le fichier de paquets {package_names} n'existe pas")
                return False

            self.log_info(f"Installation des paquets depuis le fichier {package_names}")

            # Étape 2: Lecture du fichier
            current_step += 1
            progress = int(current_step / total_steps * 100)
            self.log_info(f"[Progression: {progress}%] Lecture du fichier de paquets...")

            # Compter le nombre approximatif de paquets
            try:
                with open(package_names, 'r') as f:
                    num_packages = sum(1 for line in f if line.strip() and not line.strip().startswith('#'))
                    self.log_info(f"Nombre de paquets à installer depuis le fichier: {num_packages}")
            except Exception as e:
                self.log_warning(f"Impossible de compter les paquets: {str(e)}")

            # Étape 3: Installation
            current_step += 1
            progress = int(current_step / total_steps * 100)
            self.log_info(f"[Progression: {progress}%] Installation des paquets du fichier en cours...")

            # Construire la commande avec xargs
            base_cmd = ['xargs', '-a', package_names, 'apt-get', 'install']

            # Ajouter options selon configuration
            if assume_yes and not assume_no:
                base_cmd.append('-y')
            elif assume_no:
                base_cmd.append('--assume-no')

            # Afficher et exécuter la commande
            full_cmd = ' '.join(base_cmd)
            self.log_info(f"Exécution de: {full_cmd}")

            # Exécution en tenant compte des variables d'environnement si nécessaire
            if env_options:
                # Créer une commande bash qui définit les variables puis exécute apt-get
                env_vars = ' '.join([f"{k}='{v}'" for k, v in env_options.items()])
                bash_cmd = ['bash', '-c', f"{env_vars} {full_cmd}"]
                success, stdout, stderr = self.run_as_root(bash_cmd)
            else:
                success, stdout, stderr = self.run_as_root(base_cmd)
        else:
            # Ajouter la version si spécifiée
            if version and len(packages) == 1:
                packages[0] = f"{packages[0]}={version}"

            # Ajouter les paquets à la commande
            cmd.extend(packages)

            # Étape 2: Affichage de la commande
            current_step += 1
            progress = int(current_step / total_steps * 100)
            self.log_info(f"[Progression: {progress}%] Exécution de la commande d'installation...")

            # Afficher la commande complète
            full_cmd = ' '.join(cmd)
            self.log_info(f"Exécution de: {full_cmd}")

            # Étape 3: Installation
            current_step += 1
            progress = int(current_step / total_steps * 100)
            self.log_info(f"[Progression: {progress}%] Installation en cours...")

            # Exécution en tenant compte des variables d'environnement si nécessaire
            if env_options:
                # Créer une commande bash qui définit les variables puis exécute apt-get
                env_vars = ' '.join([f"{k}='{v}'" for k, v in env_options.items()])
                bash_cmd = ['bash', '-c', f"{env_vars} {full_cmd}"]
                success, stdout, stderr = self.run_as_root(bash_cmd, print_command=True)
            else:
                # Exécuter la commande d'installation
                success, stdout, stderr = self.run_as_root(cmd, print_command=True)

        # Étape 4: Vérification du résultat
        current_step += 1
        progress = int(current_step / total_steps * 100)

        # Traitement des erreurs et réparation si nécessaire
        if not success and auto_fix:
            if "broken packages" in stderr or "dependency problems" in stderr:
                self.log_warning(f"[Progression: {progress}%] Problème de dépendances détecté, tentative de réparation...")

                # Commande de réparation
                fix_cmd = ['apt-get', 'install', '-f']
                if assume_yes and not assume_no:
                    fix_cmd.append('-y')
                elif assume_no:
                    fix_cmd.append('--assume-no')

                fix_full_cmd = ' '.join(fix_cmd)
                self.log_info(f"Exécution de: {fix_full_cmd}")

                # Exécution de la réparation
                if env_options:
                    # Avec variables d'environnement
                    env_vars = ' '.join([f"{k}='{v}'" for k, v in env_options.items()])
                    bash_fix_cmd = ['bash', '-c', f"{env_vars} {fix_full_cmd}"]
                    fix_success, _, _ = self.run_as_root(bash_fix_cmd, print_command=True)
                else:
                    # Sans variables d'environnement
                    fix_success, _, _ = self.run_as_root(fix_cmd, print_command=True)

                if fix_success:
                    self.log_success("Réparation des dépendances réussie")
                    self.log_info(f"[Progression: {progress}%] Nouvelle tentative d'installation...")

                    # Nouvelle tentative d'installation
                    if from_file:
                        if env_options:
                            env_vars = ' '.join([f"{k}='{v}'" for k, v in env_options.items()])
                            bash_cmd = ['bash', '-c', f"{env_vars} {full_cmd}"]
                            success, _, stderr = self.run_as_root(bash_cmd)
                        else:
                            success, _, stderr = self.run_as_root(base_cmd)
                    else:
                        if env_options:
                            env_vars = ' '.join([f"{k}='{v}'" for k, v in env_options.items()])
                            bash_cmd = ['bash', '-c', f"{env_vars} {full_cmd}"]
                            success, _, stderr = self.run_as_root(bash_cmd, print_command=True)
                        else:
                            success, _, stderr = self.run_as_root(cmd, print_command=True)
                else:
                    self.log_error("Échec de la réparation des dépendances")

        # Étape 5: Finalisation
        current_step += 1
        progress = int(current_step / total_steps * 100)
        self.log_info(f"[Progression: {progress}%] Finalisation de l'installation...")

        # Afficher le résultat final
        if success:
            if not simulate:
                self.log_success(f"Installation réussie pour: {package_str}")
            else:
                self.log_info(f"Simulation d'installation terminée pour: {package_str}")
        else:
            self.log_error(f"Échec de l'installation pour: {package_str}")
            if stderr:
                # Extraire les messages d'erreur importants
                error_lines = [line for line in stderr.splitlines() if "E:" in line or "error" in line.lower()]
                for line in error_lines:
                    self.log_error(f"Erreur: {line.strip()}")

        return success

    def uninstall(self, package_names, purge=False, auto_remove=True, simulate=False):
        """
        Désinstalle un ou plusieurs paquets.

        Args:
            package_names: Nom du paquet ou liste de paquets à désinstaller
            purge: Si True, supprime également les fichiers de configuration
            auto_remove: Si True, supprime les dépendances inutilisées
            simulate: Si True, simule l'opération sans l'effectuer

        Returns:
            bool: True si la désinstallation a réussi, False sinon
        """
        # Convertir en liste si nécessaire
        if isinstance(package_names, list):
            packages = package_names
        else:
            packages = [package_names]

        action = "Simulation de la désinstallation" if simulate else "Désinstallation"
        action_type = "complète (purge)" if purge else "standard"

        # Définir les étapes
        steps = 1  # désinstallation
        if auto_remove and not simulate:
            steps += 1  # nettoyage
        self.set_total_steps(steps)

        # Étape 1: Désinstallation des paquets
        package_str = ", ".join(packages)
        self.next_step(f"{action} {action_type} des paquets: {package_str}")

        cmd = ['apt-get']

        if simulate:
            cmd.append('--simulate')
        else:
            cmd.append('-y')

        cmd.append('purge' if purge else 'remove')
        cmd.extend(packages)

        self.log_info(f"{action} {action_type} des paquets: {package_str}")
        success, _, _ = self.run_as_root(cmd)

        # Exécuter autoremove si demandé
        if success and auto_remove and not simulate:
            self.next_step("Suppression des paquets inutilisés")
            self.autoremove()

        if success:
            if not simulate:
                self.log_success(f"Désinstallation réussie pour: {package_str}")
            else:
                self.log_info(f"Simulation de désinstallation terminée pour: {package_str}")
        else:
            self.log_error(f"Échec de la désinstallation pour: {package_str}")

        return success

    def is_installed(self, package_name, min_version=None, max_version=None):
        """
        Vérifie si un paquet est installé avec contrainte de version optionnelle.

        Args:
            package_name: Nom du paquet à vérifier
            min_version: Version minimale requise (optionnel)
            max_version: Version maximale requise (optionnel)

        Returns:
            bool: True si le paquet est installé et satisfait les contraintes de version
        """
        self.log_debug(f"Vérification de l'installation du paquet {package_name}")
        success, stdout, _ = self.run(['dpkg-query', '-W', '-f=${Status} ${Version}', package_name], no_output=True)

        if not success or "install ok installed" not in stdout:
            self.log_debug(f"Le paquet {package_name} n'est pas installé")
            return False

        # Si pas de contrainte de version, c'est bon
        if not min_version and not max_version:
            self.log_debug(f"Le paquet {package_name} est installé")
            return True

        # Extraire la version installée
        parts = stdout.split()
        if len(parts) < 4:
            self.log_error(f"Format de sortie inattendu pour dpkg-query: {stdout}")
            return False

        installed_version = parts[3]

        # Vérifier les contraintes de version
        if min_version:
            if not self._compare_versions(installed_version, min_version, '>='):
                self.log_debug(f"Le paquet {package_name} est installé mais la version {installed_version} est inférieure à {min_version}")
                return False

        if max_version:
            if not self._compare_versions(installed_version, max_version, '<='):
                self.log_debug(f"Le paquet {package_name} est installé mais la version {installed_version} est supérieure à {max_version}")
                return False

        self.log_debug(f"Le paquet {package_name} version {installed_version} est installé et satisfait les contraintes de version")
        return True

    def _compare_versions(self, ver1, ver2, operator):
        """
        Compare deux versions de paquets selon l'opérateur spécifié.

        Args:
            ver1: Première version
            ver2: Seconde version
            operator: Opérateur de comparaison ('>', '<', '>=', '<=', '=')

        Returns:
            bool: Résultat de la comparaison
        """
        success, _, _ = self.run(['dpkg', '--compare-versions', ver1, operator, ver2], no_output=True)
        return success

    def get_version(self, package_name, candidate=False):
        """
        Obtient la version installée ou candidate d'un paquet.

        Args:
            package_name: Nom du paquet
            candidate: Si True, retourne la version candidate au lieu de la version installée

        Returns:
            str: Version du paquet ou None si le paquet n'est pas disponible
        """
        if candidate:
            self.log_debug(f"Récupération de la version candidate du paquet {package_name}")
            success, stdout, _ = self.run(['apt-cache', 'policy', package_name], no_output=True)

            if success:
                for line in stdout.splitlines():
                    if "Candidate:" in line:
                        version = line.split(":", 1)[1].strip()
                        if version != "(none)":
                            self.log_debug(f"Version candidate de {package_name}: {version}")
                            return version

                self.log_debug(f"Aucune version candidate trouvée pour {package_name}")
                return None
        else:
            if not self.is_installed(package_name):
                return None

            self.log_debug(f"Récupération de la version installée du paquet {package_name}")
            success, stdout, _ = self.run(['dpkg-query', '-W', '-f=${Version}', package_name], no_output=True)

            if success:
                version = stdout.strip()
                self.log_debug(f"Version installée de {package_name}: {version}")
                return version

        return None

    def get_architecture(self):
        """
        Obtient l'architecture du système.

        Returns:
            str: Architecture du système (ex: amd64, arm64, etc.)
        """
        self.log_debug("Récupération de l'architecture du système")
        success, stdout, _ = self.run(['dpkg', '--print-architecture'], no_output=True)

        if success:
            arch = stdout.strip()
            self.log_debug(f"Architecture du système: {arch}")
            return arch

        return None

    def add_repository(self, repo_line, keyring=None, key_url=None, signed_by=None, trusted=False, custom_filename=None):
        """
        Ajoute un dépôt APT au système avec contrôle précis du fichier cible.

        Args:
            repo_line: Ligne de dépôt à ajouter
            keyring: Chemin vers le fichier keyring à utiliser (optionnel)
            key_url: URL de la clé GPG à ajouter (optionnel)
            signed_by: Chemin vers le fichier de clé pour signed-by (optionnel)
            trusted: Si True, marque le dépôt comme trusted
            custom_filename: Nom de fichier personnalisé dans sources.list.d (optionnel)

        Returns:
            bool: True si l'ajout a réussi, False sinon
        """
        # Définir les étapes
        steps = 1  # ajout dépôt
        if key_url:
            steps += 1  # ajout clé
        self.set_total_steps(steps)

        # Déterminer le nom du fichier source
        if custom_filename:
            if not custom_filename.endswith('.list'):
                repo_name = custom_filename
                sources_path = f"/etc/apt/sources.list.d/{custom_filename}.list"
            else:
                repo_name = custom_filename[:-5]  # enlever l'extension .list
                sources_path = f"/etc/apt/sources.list.d/{custom_filename}"
        else:
            # Construire le nom du fichier source automatiquement
            match = re.search(r'https?://([^/]+)/?', repo_line)
            if match:
                repo_name = match.group(1).replace('.', '-')
            else:
                repo_name = "custom-repo-" + str(int(time.time()))

            sources_path = f"/etc/apt/sources.list.d/{repo_name}.list"

        # Modifier la ligne de dépôt si nécessaire
        if keyring:
            repo_line += f" [signed-by={keyring}]"
        elif signed_by:
            repo_line += f" [signed-by={signed_by}]"
        elif trusted:
            repo_line += " [trusted=yes]"

        self.next_step(f"Ajout du dépôt APT dans {sources_path}: {repo_line}")

        # Ajouter la clé GPG si fournie
        if key_url:
            self.log_info(f"Téléchargement et ajout de la clé GPG depuis {key_url}")
            key_success = False

            # Méthode 1: Télécharger et ajouter directement (moderne)
            try:
                key_file = f"/etc/apt/trusted.gpg.d/{repo_name}.gpg"
                self.log_info(f"Téléchargement de la clé vers {key_file}")
                dl_cmd = ['wget', '-qO-', key_url]
                dearmor_cmd = ['gpg', '--dearmor', '-o', key_file]

                # Exécuter les commandes en chaîne
                wget_success, key_data, _ = self.run(dl_cmd, no_output=True)
                if wget_success and key_data:
                    gpg_success, _, _ = self.run_as_root(dearmor_cmd, input_data=key_data)
                    key_success = gpg_success
            except Exception as e:
                self.log_warning(f"Erreur avec la méthode moderne: {str(e)}")

            # Méthode 2: Utiliser apt-key (déprécié mais toujours fonctionnel sur certains systèmes)
            if not key_success:
                self.log_warning("Essai avec apt-key (déprécié)")
                key_cmd = f"wget -qO- {key_url} | apt-key add -"
                key_success, _, _ = self.run_as_root(['bash', '-c', key_cmd])

            # Méthode 3: Télécharger temporairement puis convertir
            if not key_success:
                self.log_warning("Essai avec téléchargement temporaire")
                temp_key = "/tmp/temp-repo-key.gpg"
                dl_success, _, _ = self.run(['wget', '-qO', temp_key, key_url])

                if dl_success:
                    gpg_success, _, _ = self.run_as_root(['gpg', '--dearmor', '-o',
                                            f"/etc/apt/trusted.gpg.d/{repo_name}.gpg",
                                            temp_key])
                    key_success = gpg_success

                    # Supprimer le fichier temporaire
                    if os.path.exists(temp_key):
                        os.remove(temp_key)

            if not key_success:
                self.log_error(f"Échec de l'ajout de la clé GPG pour le dépôt {repo_name}")
                return False

        # Vérifier si le fichier existe déjà
        file_exists = os.path.exists(sources_path)

        if file_exists:
            # Si le fichier existe, vérifier s'il faut ajouter ou remplacer la ligne
            success, stdout, _ = self.run(['cat', sources_path], no_output=True)
            if success:
                lines = stdout.splitlines()
                found = False
                for i, line in enumerate(lines):
                    if repo_line.split()[0] in line and repo_line.split()[1] in line:
                        found = True
                        lines[i] = repo_line
                        break

                if found:
                    # Mise à jour d'une ligne existante
                    content = "\n".join(lines)
                    write_cmd = f"echo '{content}' > {sources_path}"
                else:
                    # Ajout d'une nouvelle ligne
                    write_cmd = f"echo '{repo_line}' >> {sources_path}"
            else:
                # Impossible de lire le fichier, réécrire complètement
                write_cmd = f"echo '{repo_line}' > {sources_path}"
        else:
            # Création d'un nouveau fichier
            write_cmd = f"echo '{repo_line}' > {sources_path}"

        # Écrire dans le fichier source
        self.log_info(f"Écriture de la configuration du dépôt dans {sources_path}")
        write_success, _, _ = self.run_as_root(['bash', '-c', write_cmd])

        if not write_success:
            self.log_error(f"Échec de l'écriture du fichier source {sources_path}")
            return False

        self.log_success(f"Dépôt ajouté avec succès dans {sources_path}")
        return True

    def remove_repository(self, repo_identifier, file_path=None, all_occurrences=False):
        """
        Supprime un dépôt APT du système avec recherche intelligente du fichier.

        Args:
            repo_identifier: Identifiant du dépôt (nom du fichier, contenu ou '*' pour tout supprimer)
            file_path: Nom du fichier dans sources.list.d ou chemin complet du fichier
            all_occurrences: Si True, supprime toutes les occurrences du dépôt dans tous les fichiers

        Returns:
            bool: True si la suppression a réussi, False sinon
        """
        self.set_total_steps(1)  # suppression
        self.next_step(f"Recherche et suppression du dépôt: {repo_identifier}")

        # Déterminer le chemin du fichier
        full_file_path = None
        if file_path:
            # Vérifier si c'est un chemin complet
            if file_path.startswith('/'):
                full_file_path = file_path
            else:
                # Supposer que c'est un nom de fichier dans sources.list.d
                if not file_path.endswith('.list'):
                    file_path = f"{file_path}.list"
                full_file_path = f"/etc/apt/sources.list.d/{file_path}"

        # Cas 1: Chemin du fichier fourni
        if full_file_path:
            self.log_info(f"Vérification du fichier: {full_file_path}")

            if os.path.exists(full_file_path):
                if repo_identifier == '*':
                    # Suppression complète du fichier
                    self.log_info(f"Suppression complète du fichier {full_file_path}")
                    success, _, _ = self.run_as_root(['rm', full_file_path])

                    if success:
                        self.log_success(f"Fichier de dépôt {full_file_path} supprimé avec succès")
                        return True
                    else:
                        self.log_error(f"Échec de la suppression du fichier {full_file_path}")
                        return False
                else:
                    # Modification du fichier pour supprimer uniquement certaines lignes
                    self.log_info(f"Modification du fichier {full_file_path} pour supprimer les lignes contenant '{repo_identifier}'")
                    success, stdout, _ = self.run(['cat', full_file_path], no_output=True)

                    if success:
                        # Créer un fichier temporaire sans les lignes contenant l'identifiant
                        temp_file = "/tmp/repo.list.tmp"
                        removed_count = 0
                        with open(temp_file, "w") as f:
                            for line in stdout.splitlines():
                                line_stripped = line.strip()
                                if not line_stripped or line_stripped.startswith('#'):
                                    # Garder les lignes vides et commentaires
                                    f.write(line + "\n")
                                elif repo_identifier not in line:
                                    # Garder les lignes sans l'identifiant
                                    f.write(line + "\n")
                                else:
                                    # Supprimer les lignes avec l'identifiant
                                    removed_count += 1

                        if removed_count > 0:
                            # Remplacer le fichier source par la version modifiée
                            replace_success, _, _ = self.run_as_root(['mv', temp_file, full_file_path])

                            if replace_success:
                                self.log_success(f"Dépôt supprimé de {full_file_path} ({removed_count} lignes)")
                                return True
                            else:
                                self.log_error(f"Échec de la mise à jour du fichier {full_file_path}")
                                if os.path.exists(temp_file):
                                    os.remove(temp_file)
                                return False
                        else:
                            # Aucune ligne supprimée, supprimer le fichier temporaire
                            os.remove(temp_file)
                            self.log_warning(f"Aucune ligne contenant '{repo_identifier}' n'a été trouvée dans {full_file_path}")
                            return True
            else:
                self.log_error(f"Le fichier {full_file_path} n'existe pas")
                return False

        # Cas 2: recherche par nom de fichier dans sources.list.d si repo_identifier se termine par .list
        if repo_identifier.endswith('.list') and not all_occurrences:
            sources_path = f"/etc/apt/sources.list.d/{repo_identifier}"
            if os.path.exists(sources_path):
                self.log_info(f"Suppression du fichier source {sources_path}")
                success, _, _ = self.run_as_root(['rm', sources_path])

                if success:
                    self.log_success(f"Dépôt {repo_identifier} supprimé avec succès")
                    return True
                else:
                    self.log_error(f"Échec de la suppression du fichier source {sources_path}")
                    return False

        # Cas 3: Recherche dans tous les fichiers .list du répertoire sources.list.d
        found = False
        sources_dir = "/etc/apt/sources.list.d"
        if os.path.exists(sources_dir):
            self.log_info(f"Recherche de '{repo_identifier}' dans le répertoire {sources_dir}")
            modified_files = 0

            for file in os.listdir(sources_dir):
                if file.endswith('.list'):
                    file_path = os.path.join(sources_dir, file)
                    success, stdout, _ = self.run(['cat', file_path], no_output=True)

                    if success and repo_identifier in stdout:
                        if all_occurrences:
                            # Modification du fichier pour retirer les lignes contenant l'identifiant
                            temp_file = "/tmp/repo.list.tmp"
                            removed_count = 0
                            with open(temp_file, "w") as f:
                                for line in stdout.splitlines():
                                    line_stripped = line.strip()
                                    if not line_stripped or line_stripped.startswith('#'):
                                        # Garder les lignes vides et commentaires
                                        f.write(line + "\n")
                                    elif repo_identifier not in line:
                                        # Garder les lignes sans l'identifiant
                                        f.write(line + "\n")
                                    else:
                                        # Supprimer les lignes avec l'identifiant
                                        removed_count += 1

                            if removed_count > 0:
                                self.log_info(f"Suppression de {removed_count} lignes contenant '{repo_identifier}' dans {file_path}")
                                replace_success, _, _ = self.run_as_root(['mv', temp_file, file_path])

                                if replace_success:
                                    self.log_success(f"Dépôt modifié: {file_path}")
                                    modified_files += 1
                                    found = True
                                else:
                                    self.log_error(f"Échec de la mise à jour du fichier {file_path}")
                                    if os.path.exists(temp_file):
                                        os.remove(temp_file)
                            else:
                                # Aucune ligne supprimée, supprimer le fichier temporaire
                                if os.path.exists(temp_file):
                                    os.remove(temp_file)
                        else:
                            # Suppression complète du fichier (si pas all_occurrences)
                            self.log_info(f"Dépôt trouvé dans {file_path}, suppression du fichier")
                            rm_success, _, _ = self.run_as_root(['rm', file_path])
                            if rm_success:
                                self.log_success(f"Dépôt supprimé via {file_path}")
                                found = True
                                # On a trouvé et supprimé un fichier, on peut s'arrêter
                                break
                            else:
                                self.log_error(f"Échec de la suppression du fichier {file_path}")

            if all_occurrences and modified_files > 0:
                self.log_success(f"Dépôt '{repo_identifier}' supprimé de {modified_files} fichiers")

        # Cas 4: Recherche dans le fichier sources.list principal si rien n'a été trouvé ou all_occurrences
        sources_path = "/etc/apt/sources.list"
        if os.path.exists(sources_path) and (all_occurrences or not found):
            self.log_info(f"Recherche de '{repo_identifier}' dans {sources_path}")
            success, stdout, _ = self.run(['cat', sources_path], no_output=True)

            if success and repo_identifier in stdout:
                # Créer un fichier temporaire sans les lignes contenant l'identifiant
                temp_file = "/tmp/sources.list.tmp"
                removed_count = 0
                with open(temp_file, "w") as f:
                    for line in stdout.splitlines():
                        line_stripped = line.strip()
                        if not line_stripped or line_stripped.startswith('#'):
                            # Garder les lignes vides et commentaires
                            f.write(line + "\n")
                        elif repo_identifier not in line:
                            # Garder les lignes sans l'identifiant
                            f.write(line + "\n")
                        else:
                            # Supprimer les lignes avec l'identifiant
                            removed_count += 1

                if removed_count > 0:
                    # Remplacer le fichier sources.list
                    self.log_info(f"Dépôt trouvé dans {sources_path}, modification du fichier ({removed_count} lignes)")
                    success, _, _ = self.run_as_root(['mv', temp_file, sources_path])

                    if success:
                        self.log_success(f"Dépôt supprimé de {sources_path}")
                        found = True
                    else:
                        self.log_error(f"Échec de la mise à jour du fichier {sources_path}")
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                else:
                    # Aucune ligne supprimée, supprimer le fichier temporaire
                    if os.path.exists(temp_file):
                        os.remove(temp_file)

        if found:
            return True
        else:
            self.log_warning(f"Aucun dépôt correspondant à '{repo_identifier}' n'a été trouvé")
            return False

    def search(self, pattern, installed_only=False, names_only=False, full_details=False):
        """
        Recherche des paquets correspondant à un motif.

        Args:
            pattern: Motif de recherche
            installed_only: Si True, recherche uniquement parmi les paquets installés
            names_only: Si True, retourne uniquement les noms de paquets
            full_details: Si True, retourne tous les détails disponibles

        Returns:
            list: Liste des paquets trouvés
        """
        self.log_info(f"Recherche de paquets correspondant à '{pattern}'")

        if installed_only:
            cmd = ['dpkg', '--list']
        else:
            cmd = ['apt-cache', 'search', pattern]

        success, stdout, _ = self.run(cmd, no_output=True)

        if not success:
            self.log_error(f"Échec de la recherche de paquets")
            return []

        results = []

        if installed_only:
            for line in stdout.splitlines():
                if line.startswith('ii '):
                    parts = line.split()
                    if len(parts) >= 2 and pattern.lower() in parts[1].lower():
                        if names_only:
                            results.append(parts[1])
                        elif full_details:
                            pkg_info = {
                                'name': parts[1],
                                'version': parts[2],
                                'architecture': parts[3] if len(parts) > 3 else '',
                                'description': ' '.join(parts[4:]) if len(parts) > 4 else ''
                            }
                            results.append(pkg_info)
                        else:
                            results.append({
                                'name': parts[1],
                                'version': parts[2]
                            })
        else:
            for line in stdout.splitlines():
                if " - " in line:
                    name, description = line.split(" - ", 1)

                    if names_only:
                        results.append(name.strip())
                    elif full_details:
                        # Obtenir plus de détails via apt-cache show
                        pkg_success, pkg_stdout, _ = self.run(['apt-cache', 'show', name.strip()], no_output=True)

                        if pkg_success:
                            pkg_info = {
                                'name': name.strip(),
                                'description': description.strip(),
                                'version': '',
                                'architecture': '',
                                'size': '',
                                'section': '',
                                'maintainer': ''
                            }

                            for pkg_line in pkg_stdout.splitlines():
                                if ': ' in pkg_line:
                                    key, value = pkg_line.split(': ', 1)
                                    if key == 'Version':
                                        pkg_info['version'] = value
                                    elif key == 'Architecture':
                                        pkg_info['architecture'] = value
                                    elif key == 'Installed-Size':
                                        pkg_info['size'] = value
                                    elif key == 'Section':
                                        pkg_info['section'] = value
                                    elif key == 'Maintainer':
                                        pkg_info['maintainer'] = value

                            results.append(pkg_info)
                    else:
                        results.append({
                            'name': name.strip(),
                            'description': description.strip()
                        })

        self.log_info(f"Recherche terminée, {len(results)} paquets trouvés")
        return results

    def autoremove(self, purge=False, simulate=False):
        """
        Supprime les paquets qui ne sont plus nécessaires.

        Args:
            purge: Si True, supprime également les fichiers de configuration
            simulate: Si True, simule l'opération sans l'effectuer

        Returns:
            bool: True si l'opération a réussi, False sinon
        """
        cmd = ['apt-get', 'autoremove']

        if purge:
            cmd.append('--purge')

        if simulate:
            cmd.append('--simulate')
        else:
            cmd.append('-y')

        action = "Simulation du nettoyage" if simulate else "Nettoyage"
        self.log_info(f"{action} des paquets inutilisés")

        success, _, _ = self.run_as_root(cmd)

        if success:
            if not simulate:
                self.log_success("Paquets inutilisés supprimés avec succès")
            else:
                self.log_info("Simulation de nettoyage terminée")
        else:
            self.log_error("Échec du nettoyage des paquets inutilisés")

        return success

    def clean(self, all_cache=False):
        """
        Nettoie le cache apt.

        Args:
            all_cache: Si True, supprime tous les packages téléchargés (clean), sinon uniquement les obsolètes (autoclean)

        Returns:
            bool: True si l'opération a réussi, False sinon
        """
        cmd = ['apt-get', 'clean' if all_cache else 'autoclean']

        action = "Nettoyage complet" if all_cache else "Nettoyage automatique"
        self.log_info(f"{action} du cache apt")

        success, _, _ = self.run_as_root(cmd)

        if success:
            self.log_success(f"{action} du cache terminé avec succès")
        else:
            self.log_error(f"Échec du {action.lower()} du cache")

        return success

    def fix_broken(self, simulate=False):
        """
        Répare les paquets cassés.

        Args:
            simulate: Si True, simule l'opération sans l'effectuer

        Returns:
            bool: True si la réparation a réussi, False sinon
        """
        cmd = ['apt-get', 'install', '-f']

        if simulate:
            cmd.append('--simulate')
        else:
            cmd.append('-y')

        action = "Simulation de la réparation" if simulate else "Réparation"
        self.log_info(f"{action} des paquets cassés")

        success, _, _ = self.run_as_root(cmd)

        if success:
            if not simulate:
                self.log_success("Paquets cassés réparés avec succès")
            else:
                self.log_info("Simulation de réparation terminée")
        else:
            self.log_error("Échec de la réparation des paquets cassés")

        return success

    def get_installed_size(self, package_name):
        """
        Obtient la taille installée d'un paquet en kB.

        Args:
            package_name: Nom du paquet

        Returns:
            int: Taille du paquet en kB ou -1 si erreur
        """
        if not self.is_installed(package_name):
            return -1

        self.log_debug(f"Récupération de la taille installée du paquet {package_name}")
        success, stdout, _ = self.run(['dpkg-query', '-W', '-f=${Installed-Size}', package_name], no_output=True)

        if success:
            try:
                size = int(stdout.strip())
                self.log_debug(f"Taille installée de {package_name}: {size} kB")
                return size
            except ValueError:
                self.log_error(f"Impossible de convertir la taille en entier: {stdout}")
                return -1

        return -1

    def get_download_size(self, package_name, version=None):
        """
        Obtient la taille de téléchargement d'un paquet en B.

        Args:
            package_name: Nom du paquet
            version: Version spécifique (optionnel)

        Returns:
            int: Taille de téléchargement du paquet en B ou -1 si erreur
        """
        cmd = ['apt-cache', 'show']

        if version:
            cmd.extend([f"{package_name}={version}"])
        else:
            cmd.append(package_name)

        self.log_debug(f"Récupération de la taille de téléchargement du paquet {package_name}")
        success, stdout, _ = self.run(cmd, no_output=True)

        if success:
            for line in stdout.splitlines():
                if line.startswith("Size: "):
                    try:
                        size = int(line.split(":", 1)[1].strip())
                        self.log_debug(f"Taille de téléchargement de {package_name}: {size} B")
                        return size
                    except ValueError:
                        self.log_error(f"Impossible de convertir la taille en entier: {line}")
                        return -1

        return -1

    def get_dependencies(self, package_name, recursive=False, installed_only=False):
        """
        Obtient les dépendances d'un paquet.

        Args:
            package_name: Nom du paquet
            recursive: Si True, obtient les dépendances récursives
            installed_only: Si True, retourne uniquement les dépendances installées

        Returns:
            list: Liste des dépendances
        """
        if recursive:
            cmd = ['apt-rdepends', package_name]
            self.log_debug(f"Récupération des dépendances récursives du paquet {package_name}")
        else:
            cmd = ['apt-cache', 'depends', package_name]
            self.log_debug(f"Récupération des dépendances directes du paquet {package_name}")

        success, stdout, _ = self.run(cmd, no_output=True)

        if not success:
            self.log_error(f"Échec de la récupération des dépendances pour {package_name}")
            return []

        dependencies = []

        if recursive:
            # Format de apt-rdepends:
            # package_name
            #   Depends: dep1
            #   Depends: dep2
            # dep1
            #   Depends: dep1_1
            for line in stdout.splitlines():
                if "Depends:" in line:
                    dep = line.split(":", 1)[1].strip()
                    if dep not in dependencies and dep != package_name:
                        dependencies.append(dep)
        else:
            # Format de apt-cache depends:
            # package_name
            #   Depends: dep1
            #   Depends: dep2
            #   Recommends: rec1
            for line in stdout.splitlines():
                if line.strip().startswith("Depends:"):
                    dep = line.split(":", 1)[1].strip()
                    if dep not in dependencies and dep != package_name:
                        dependencies.append(dep)

        # Filtrer les dépendances installées si demandé
        if installed_only:
            installed_deps = []
            for dep in dependencies:
                if self.is_installed(dep):
                    installed_deps.append(dep)
            dependencies = installed_deps

        self.log_debug(f"Dépendances de {package_name}: {', '.join(dependencies) if dependencies else 'aucune'}")
        return dependencies

    def get_reverse_dependencies(self, package_name, installed_only=False):
        """
        Obtient les paquets qui dépendent du paquet spécifié.

        Args:
            package_name: Nom du paquet
            installed_only: Si True, retourne uniquement les paquets installés

        Returns:
            list: Liste des paquets qui dépendent du paquet spécifié
        """
        self.log_debug(f"Récupération des dépendances inverses du paquet {package_name}")
        success, stdout, _ = self.run(['apt-cache', 'rdepends', package_name], no_output=True)

        if not success:
            self.log_error(f"Échec de la récupération des dépendances inverses pour {package_name}")
            return []

        reverse_deps = []

        # Format de apt-cache rdepends:
        # package_name
        # Reverse Depends:
        #   dep1
        #   dep2
        started = False
        for line in stdout.splitlines():
            if "Reverse Depends:" in line:
                started = True
                continue

            if started and line.strip() and not line.startswith(" "):
                # Nouvelle section, on arrête
                break

            if started and line.strip():
                dep = line.strip()
                if dep not in reverse_deps and dep != package_name:
                    reverse_deps.append(dep)

        # Filtrer les dépendances installées si demandé
        if installed_only:
            installed_deps = []
            for dep in reverse_deps:
                if self.is_installed(dep):
                    installed_deps.append(dep)
            reverse_deps = installed_deps

        self.log_debug(f"Dépendances inverses de {package_name}: {', '.join(reverse_deps) if reverse_deps else 'aucune'}")
        return reverse_deps

    def hold_package(self, package_name):
        """
        Bloque un paquet pour empêcher sa mise à jour automatique.

        Args:
            package_name: Nom du paquet à bloquer

        Returns:
            bool: True si l'opération a réussi, False sinon
        """
        self.log_info(f"Blocage du paquet {package_name} pour empêcher sa mise à jour")
        success, _, _ = self.run_as_root(['apt-mark', 'hold', package_name])

        if success:
            self.log_success(f"Paquet {package_name} bloqué avec succès")
        else:
            self.log_error(f"Échec du blocage du paquet {package_name}")

        return success

    def unhold_package(self, package_name):
        """
        Débloque un paquet pour permettre sa mise à jour automatique.

        Args:
            package_name: Nom du paquet à débloquer

        Returns:
            bool: True si l'opération a réussi, False sinon
        """
        self.log_info(f"Déblocage du paquet {package_name} pour permettre sa mise à jour")
        success, _, _ = self.run_as_root(['apt-mark', 'unhold', package_name])

        if success:
            self.log_success(f"Paquet {package_name} débloqué avec succès")
        else:
            self.log_error(f"Échec du déblocage du paquet {package_name}")

        return success

    def is_held(self, package_name):
        """
        Vérifie si un paquet est bloqué.

        Args:
            package_name: Nom du paquet à vérifier

        Returns:
            bool: True si le paquet est bloqué, False sinon
        """
        self.log_debug(f"Vérification si le paquet {package_name} est bloqué")
        success, stdout, _ = self.run(['apt-mark', 'showhold'], no_output=True)

        if success and package_name in stdout.splitlines():
            self.log_debug(f"Le paquet {package_name} est bloqué")
            return True
        else:
            self.log_debug(f"Le paquet {package_name} n'est pas bloqué")
            return False

    def get_package_info(self, package_name):
        """
        Obtient des informations détaillées sur un paquet.

        Args:
            package_name: Nom du paquet

        Returns:
            dict: Informations sur le paquet ou None si erreur
        """
        self.log_debug(f"Récupération des informations détaillées du paquet {package_name}")

        # Vérifier si le paquet est disponible
        success, stdout, _ = self.run(['apt-cache', 'show', package_name], no_output=True)

        if not success:
            self.log_error(f"Paquet {package_name} non trouvé")
            return None

        info = {
            'name': package_name,
            'installed': self.is_installed(package_name),
            'held': self.is_held(package_name),
            'version_installed': None,
            'version_candidate': None,
            'architecture': None,
            'section': None,
            'priority': None,
            'description': None,
            'maintainer': None,
            'size': None,
            'homepage': None,
            'source': None
        }

        # Obtenir la version candidate
        policy_success, policy_stdout, _ = self.run(['apt-cache', 'policy', package_name], no_output=True)
        if policy_success:
            for line in policy_stdout.splitlines():
                if "Installed:" in line:
                    version = line.split(":", 1)[1].strip()
                    if version != "(none)":
                        info['version_installed'] = version
                elif "Candidate:" in line:
                    version = line.split(":", 1)[1].strip()
                    if version != "(none)":
                        info['version_candidate'] = version

        # Obtenir les détails du paquet
        current_key = None
        multiline_value = []

        for line in stdout.splitlines():
            if not line.strip():
                # Ligne vide, terminer la valeur multiline si nécessaire
                if current_key and multiline_value:
                    value = "\n".join(multiline_value)
                    if current_key == 'Description':
                        info['description'] = value
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

                if key == 'Architecture':
                    info['architecture'] = value
                elif key == 'Section':
                    info['section'] = value
                elif key == 'Priority':
                    info['priority'] = value
                elif key == 'Maintainer':
                    info['maintainer'] = value
                elif key == 'Installed-Size':
                    try:
                        info['size'] = int(value)
                    except ValueError:
                        info['size'] = value
                elif key == 'Homepage':
                    info['homepage'] = value
                elif key == 'Source':
                    info['source'] = value
                elif key == 'Description':
                    multiline_value = [value]

        # Capture la dernière valeur multiline si nécessaire
        if current_key and multiline_value:
            value = "\n".join(multiline_value)
            if current_key == 'Description':
                info['description'] = value

        self.log_debug(f"Informations détaillées récupérées pour {package_name}")
        return info

    def get_upgradable_packages(self, security_only=False):
        """
        Obtient la liste des paquets pouvant être mis à jour.

        Args:
            security_only: Si True, retourne uniquement les mises à jour de sécurité

        Returns:
            list: Liste des paquets pouvant être mis à jour
        """
        self.set_total_steps(2)  # mise à jour des sources + analyse

        self.next_step("Mise à jour des sources apt")
        self.update(allow_fail=True)

        self.next_step("Analyse des paquets à mettre à jour")
        security_label = " de sécurité" if security_only else ""
        self.log_info(f"Récupération de la liste des paquets{security_label} pouvant être mis à jour")

        success, stdout, _ = self.run(['apt-get', 'upgrade', '--simulate'], no_output=True)

        if not success:
            self.log_error("Échec de la récupération des paquets à mettre à jour")
            return []

        upgradable = []
        started = False

        for line in stdout.splitlines():
            if "The following packages will be upgraded:" in line:
                started = True
                continue

            if started and "upgraded," in line:
                # Fin de la liste
                break

            if started and line.strip():
                packages = line.strip().split()
                upgradable.extend(packages)

        # Filtrer les mises à jour de sécurité si demandé
        if security_only and upgradable:
            security_upgrades = []

            # Créer une liste temporaire de sources de sécurité
            tmp_sources = "/tmp/security-sources.list"
            success, stdout, _ = self.run(['cat', '/etc/apt/sources.list'], no_output=True)

            if success:
                with open(tmp_sources, "w") as f:
                    for line in stdout.splitlines():
                        if "security" in line and not line.strip().startswith("#"):
                            f.write(line + "\n")

                # Vérifier aussi dans sources.list.d
                if os.path.exists("/etc/apt/sources.list.d"):
                    for file in os.listdir("/etc/apt/sources.list.d"):
                        if file.endswith(".list"):
                            success, stdout, _ = self.run(['cat', f'/etc/apt/sources.list.d/{file}'], no_output=True)
                            if success:
                                for line in stdout.splitlines():
                                    if "security" in line and not line.strip().startswith("#"):
                                        f.write(line + "\n")

            # Utiliser la liste temporaire pour vérifier les mises à jour de sécurité
            self.log_info("Filtrage des mises à jour de sécurité")
            sec_success, sec_stdout, _ = self.run_as_root([
                'apt-get', 'upgrade', '--simulate',
                '-o', f'Dir::Etc::SourceList={tmp_sources}'
            ], no_output=True)

            if sec_success:
                started = False
                for line in sec_stdout.splitlines():
                    if "The following packages will be upgraded:" in line:
                        started = True
                        continue

                    if started and "upgraded," in line:
                        # Fin de la liste
                        break

                    if started and line.strip():
                        packages = line.strip().split()
                        security_upgrades.extend(packages)

            # Supprimer le fichier temporaire
            if os.path.exists(tmp_sources):
                os.remove(tmp_sources)

            upgradable = security_upgrades

        self.log_info(f"Paquets pouvant être mis à jour: {', '.join(upgradable) if upgradable else 'aucun'}")
        return upgradable

    def download_package(self, package_name, version=None, destination=None):
        """
        Télécharge un paquet sans l'installer.

        Args:
            package_name: Nom du paquet à télécharger
            version: Version spécifique à télécharger (optionnel)
            destination: Répertoire de destination (optionnel)

        Returns:
            str: Chemin du fichier téléchargé ou None si erreur
        """
        self.set_total_steps