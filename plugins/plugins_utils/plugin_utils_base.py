# install/plugins/plugins_utils/plugin_utils_base.py
#!/usr/bin/env python3
"""
Module utilitaire de base pour les plugins.
Fournit une classe de base avec des fonctionnalités communes de journalisation,
d'exécution de commandes (avec gestion root) et de gestion de la progression.
"""

import os
import subprocess
import traceback
import time
import threading
import shlex # Pour découper les commandes en chaîne de manière sécurisée
from typing import Union, Optional, List, Tuple, Dict, Any

# Essayer d'importer PluginLogger de manière sécurisée
try:
    # Assumer que PluginLogger est dans le même répertoire ou accessible via le path
    from .plugin_logger import PluginLogger
except ImportError:
    # Fallback si PluginLogger n'est pas disponible
    print("Avertissement: PluginLogger non trouvé, utilisation d'un logger basique.")
    # Définir une classe PluginLogger minimale pour éviter les erreurs AttributeError
    class PluginLogger:
        def __init__(self, *args, **kwargs): pass
        def info(self, msg: str, **kwargs): print(f"[INFO] {msg}")
        def warning(self, msg: str, **kwargs): print(f"[WARN] {msg}")
        def error(self, msg: str, **kwargs): print(f"[ERROR] {msg}")
        def debug(self, msg: str, **kwargs): print(f"[DEBUG] {msg}")
        def success(self, msg: str, **kwargs): print(f"[SUCCESS] {msg}")
        def set_total_steps(self, total: int, pb_id: Optional[str]): pass
        def next_step(self, pb_id: Optional[str], current_step: Optional[int] = None): pass
        def create_bar(self, *args, **kwargs): pass
        def update_bar(self, *args, **kwargs): pass
        def delete_bar(self, *args, **kwargs): pass
        def next_bar(self, *args, **kwargs): pass

DEFAULT_COMMAND_TIMEOUT = 300 # 5 minutes par défaut

class PluginUtilsBase:
    """
    Classe de base pour les utilitaires de plugins. Fournit la journalisation,
    l'exécution de commandes et la gestion de la progression.
    Assume par défaut que les commandes nécessitant des privilèges élevés
    seront exécutées en tant que root (via sudo si nécessaire).
    """

    def __init__(self, logger: Optional[PluginLogger] = None, target_ip: Optional[str] = None):
        """
        Initialise un utilitaire de base pour les plugins.

        Args:
            logger: Instance de PluginLogger à utiliser pour la journalisation (optionnel).
                    Si None, une nouvelle instance sera créée.
            target_ip: Adresse IP cible pour les logs (utile pour les exécutions SSH).
        """
        self.logger = logger if logger else PluginLogger()
        self.target_ip = target_ip
        try:
            # Vérifier une seule fois si on est root
            self._is_root = (os.geteuid() == 0)
        except AttributeError:
             # Peut échouer sur certains systèmes non-Unix (ex: Windows)
             self._is_root = False # Supposer non-root si euid n'existe pas
        self._current_task_id: Optional[str] = None
        self._task_total_steps: int = 1
        self._task_current_step: int = 0

        # Variables pour la gestion des barres visuelles
        self.use_visual_bars = True

    # --- Méthodes de Logging (Déléguées au logger) ---

    def log_info(self, msg: str):
        """Enregistre un message d'information."""
        self.logger.info(msg, target_ip=self.target_ip)

    def log_warning(self, msg: str):
        """Enregistre un message d'avertissement."""
        self.logger.warning(msg, target_ip=self.target_ip)

    def log_error(self, msg: str, exc_info: bool = False):
        """
        Enregistre un message d'erreur.

        Args:
            msg: Le message d'erreur.
            exc_info: Si True, ajoute le traceback de l'exception actuelle.
        """
        self.logger.error(msg, target_ip=self.target_ip)
        if exc_info:
             # Utiliser traceback.format_exc() pour obtenir le traceback formaté
             self.logger.error(f"Traceback:\n{traceback.format_exc()}", target_ip=self.target_ip)

    def log_debug(self, msg: str):
        """Enregistre un message de débogage."""
        self.logger.debug(msg, target_ip=self.target_ip)

    def log_success(self, msg: str):
        """Enregistre un message de succès."""
        self.logger.success(msg, target_ip=self.target_ip)

    # --- Méthodes de Gestion de Progression ---

    def start_task(self, total_steps: int, description: str = "", task_id: Optional[str] = None):
        """
        Démarre une nouvelle tâche avec un nombre défini d'étapes pour le suivi de progression.

        Args:
            total_steps: Nombre total d'étapes pour cette tâche.
            description: Description de la tâche (affichée avec la barre de progression).
            task_id: Identifiant unique pour la tâche (utile pour plusieurs tâches parallèles).
                     Si None, utilise un ID basé sur le timestamp.
        """
        self._current_task_id = task_id or f"task_{int(time.time())}"
        self._task_total_steps = max(1, total_steps) # Assurer au moins 1 étape
        self._task_current_step = 0
        self.logger.set_total_steps(self._task_total_steps, self._current_task_id)

        if self.use_visual_bars:
            # Utiliser la description comme pre_text pour la barre visuelle
            self.logger.create_bar(self._current_task_id, self._task_total_steps, pre_text=description)
        else:
             self.log_info(f"Démarrage tâche: {description} ({self._task_total_steps} étapes)")

    def update_task(self, advance: int = 1, description: Optional[str] = None):
        """
        Met à jour la progression de la tâche en cours.

        Args:
            advance: Nombre d'étapes à avancer (par défaut 1).
            description: Nouvelle description à afficher pour cette étape (optionnel).
        """
        if self._current_task_id is None:
            self.log_warning("Impossible de mettre à jour : aucune tâche démarrée.")
            return

        self._task_current_step += advance
        # S'assurer que l'étape actuelle ne dépasse pas le total
        current = min(self._task_current_step, self._task_total_steps)

        # Mettre à jour la progression numérique via le logger
        # Le logger calcule le pourcentage basé sur current/total
        self.logger.next_step(self._current_task_id, current_step=current)

        # Mettre à jour la barre visuelle si activée
        if self.use_visual_bars:
            # Utiliser la description fournie ou un format par défaut pour le post_text
            step_text = description if description else f"{current}/{self._task_total_steps}"
            # Utiliser next_bar pour avancer la barre visuelle
            self.logger.next_bar(self._current_task_id, current_step=current, post_text=step_text)
        elif description:
            # Afficher la description comme log si pas de barre visuelle
             self.log_info(description)

    def complete_task(self, success: bool = True, message: Optional[str] = None):
        """
        Marque la tâche en cours comme terminée.

        Args:
            success: Indique si la tâche s'est terminée avec succès.
            message: Message final à afficher (optionnel).
        """
        if self._current_task_id is None:
            self.log_warning("Impossible de compléter : aucune tâche démarrée.")
            return # Aucune tâche active

        final_step = self._task_total_steps

        # Mettre à jour la progression numérique à 100%
        self.logger.next_step(self._current_task_id, current_step=final_step)

        # Mettre à jour/supprimer la barre visuelle
        if self.use_visual_bars:
            final_text = message or ("Terminé" if success else "Échec")
            final_color = "green" if success else "red"
            # Mettre à jour une dernière fois avant de supprimer
            self.logger.update_bar(
                self._current_task_id,
                final_step,
                None, # total non changé
                pre_text=final_text, # Afficher le message final avant la barre
                color=final_color
            )
            # Optionnel: supprimer la barre après un court délai
            # self.logger.delete_bar(self._current_task_id)
            # Pour l'instant, on la laisse affichée à 100%
        elif message:
            # Afficher le message final si pas de barre visuelle
            if success:
                self.log_success(message)
            else:
                self.log_error(message)

        # Réinitialiser l'état de la tâche
        self._current_task_id = None
        self._task_total_steps = 1
        self._task_current_step = 0

    def enable_visual_bars(self, enable: bool = True):
        """Active ou désactive l'utilisation des barres de progression visuelles."""
        self.use_visual_bars = enable

    # --- Méthodes d'Exécution de Commandes ---

    def run(self,
            cmd: Union[str, List[str]],
            input_data: Optional[str] = None,
            no_output: bool = False,
            print_command: bool = False,
            real_time_output: bool = False, # Note: Peut être moins fiable avec sudo/input
            error_as_warning: bool = False,
            timeout: Optional[int] = DEFAULT_COMMAND_TIMEOUT,
            check: bool = False, # Par défaut False pour retourner succès/échec
            shell: bool = False,
            cwd: Optional[str] = None,
            env: Optional[Dict[str, str]] = None,
            needs_sudo: Optional[bool] = None) -> Tuple[bool, str, str]:
        """
        Exécute une commande système, en utilisant sudo si nécessaire et non déjà root.

        Args:
            cmd: Commande à exécuter (chaîne ou liste d'arguments).
                 Si chaîne et shell=False, elle sera découpée avec shlex.
            input_data: Données à envoyer sur stdin (optionnel).
            no_output: Si True, ne journalise pas stdout/stderr.
            print_command: Si True, journalise la commande avant exécution.
            real_time_output: Si True, tente d'afficher la sortie en temps réel.
                              Peut être moins fiable avec sudo ou input_data.
            error_as_warning: Si True, traite les erreurs (stderr) comme des avertissements.
            timeout: Timeout en secondes pour la commande (None pour aucun timeout).
            check: Si True, lève une exception CalledProcessError en cas d'échec.
                   Si False (par défaut), retourne le succès basé sur le code de retour.
            shell: Si True, exécute la commande via le shell système (attention sécurité).
            cwd: Répertoire de travail pour la commande (optionnel).
            env: Variables d'environnement pour la commande (optionnel). Si None,
                 l'environnement actuel est hérité. Si fourni, il remplace l'env.
            needs_sudo: Forcer l'utilisation de sudo (True), forcer la non-utilisation (False),
                        ou laisser la détection automatique (None, défaut).

        Returns:
            Tuple (success: bool, stdout: str, stderr: str).
            'success' est True si le code de retour est 0.

        Raises:
            subprocess.CalledProcessError: Si la commande échoue et check=True.
            subprocess.TimeoutExpired: Si le timeout est dépassé.
            FileNotFoundError: Si la commande ou sudo n'est pas trouvée.
            PermissionError: Si sudo est nécessaire mais échoue (ex: mauvais mdp).
        """
        # 1. Préparation de la commande
        if isinstance(cmd, str) and not shell:
             try:
                 cmd_list = shlex.split(cmd)
             except ValueError as e:
                 self.log_error(f"Erreur lors du découpage de la commande: '{cmd}'. Erreur: {e}")
                 raise ValueError(f"Commande invalide: {cmd}") from e
        elif isinstance(cmd, list):
             cmd_list = cmd
        elif isinstance(cmd, str) and shell:
             cmd_list = cmd # Le shell interprétera la chaîne
        else:
             raise TypeError("La commande doit être une chaîne ou une liste d'arguments.")

        # 2. Détermination de l'utilisation de sudo
        use_sudo = False
        if needs_sudo is True:
            if self._is_root:
                 self.log_debug("needs_sudo=True mais déjà root, sudo non utilisé.")
            else:
                 use_sudo = True
        elif needs_sudo is None and not self._is_root:
            # Détection automatique: si pas root, on utilise sudo
            use_sudo = True

        sudo_password = None
        if use_sudo:
            # Vérifier si sudo est disponible
            if subprocess.run(['which', 'sudo'], capture_output=True, text=True).returncode != 0:
                self.log_error("Commande 'sudo' non trouvée. Impossible d'exécuter avec des privilèges élevés.")
                raise FileNotFoundError("sudo n'est pas installé ou pas dans le PATH")

            # Préparer la commande sudo
            # Utiliser -S pour lire le mot de passe depuis stdin si besoin
            # Utiliser -E pour préserver l'environnement si env n'est pas fourni
            sudo_prefix = ["sudo", "-S"]
            effective_env = env # Par défaut, utiliser l'env fourni
            if env is None:
                 sudo_prefix.append("-E")
                 effective_env = os.environ.copy() # Hériter et potentiellement modifier

            # Récupérer le mot de passe sudo depuis l'environnement (défini par ssh_wrapper)
            sudo_password = os.environ.get("SUDO_PASSWORD")
            if not sudo_password:
                 self.log_warning("Sudo nécessaire mais aucun mot de passe SUDO_PASSWORD trouvé dans l'environnement. Sudo peut échouer.")
                 # On continue quand même, sudo peut être configuré sans mot de passe

            if isinstance(cmd_list, list):
                 cmd_to_run = sudo_prefix + cmd_list
            else: # shell=True
                 # Construire la commande shell avec sudo
                 # shlex.quote est essentiel pour la sécurité
                 quoted_cmd = shlex.quote(cmd_list)
                 cmd_to_run = f"{' '.join(sudo_prefix)} sh -c {quoted_cmd}"
                 shell = True # Assurer que shell est True pour Popen
                 self.log_warning("Utilisation combinée de sudo et shell=True. Vérifier la commande.")

        else:
            cmd_to_run = cmd_list
            effective_env = env # Utiliser l'env fourni ou None (héritage par Popen)

        # 3. Logging de la commande (masquer le mot de passe)
        cmd_str_for_log = ' '.join(cmd_to_run) if isinstance(cmd_to_run, list) else cmd_to_run
        if print_command:
            logged_cmd = cmd_str_for_log
            if sudo_password:
                 logged_cmd = logged_cmd.replace(sudo_password, '********')
            self.log_info(f"Exécution: {logged_cmd}")

        # 4. Exécution avec subprocess.Popen
        stdout_data = []
        stderr_data = []
        process = None
        start_time = time.monotonic()

        try:
            process = subprocess.Popen(
                cmd_to_run,
                stdin=subprocess.PIPE, # Toujours créer stdin pour passer le mot de passe sudo
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, # Important pour l'encodage
                shell=shell,
                cwd=cwd,
                env=effective_env, # Utiliser l'environnement effectif
                bufsize=1, # Lecture ligne par ligne
                universal_newlines=True # Compatibilité Windows/Unix pour les fins de ligne
            )

            # 5. Gestion de l'input (y compris le mot de passe sudo)
            input_full = ""
            if use_sudo and sudo_password:
                 input_full += sudo_password + "\n" # Ajouter le mot de passe sudo
            if input_data is not None:
                 input_full += input_data

            # 6. Communication avec le processus (gestion stdout/stderr/timeout)
            try:
                # Utiliser communicate pour gérer l'input, la sortie et le timeout de manière fiable
                stdout_res, stderr_res = process.communicate(input=input_full if input_full else None, timeout=timeout)
                if stdout_res: stdout_data = stdout_res.splitlines()
                if stderr_res: stderr_data = stderr_res.splitlines()

            except subprocess.TimeoutExpired:
                 elapsed = time.monotonic() - start_time
                 self.log_error(f"Timeout ({timeout}s, écoulé: {elapsed:.2f}s) dépassé pour la commande: {cmd_str_for_log}")
                 process.kill()
                 # Essayer de lire ce qui reste après kill
                 stdout_res, stderr_res = process.communicate()
                 if stdout_res: stdout_data.extend(stdout_res.splitlines())
                 if stderr_res: stderr_data.extend(stderr_res.splitlines())
                 # Relancer l'exception
                 raise
            except Exception as comm_error:
                 # Gérer d'autres erreurs potentielles de communication
                 self.log_error(f"Erreur de communication avec le processus: {comm_error}", exc_info=True)
                 # Essayer de récupérer le code de retour si possible
                 process.poll() # Mettre à jour returncode

            # 7. Récupération du code de retour
            return_code = process.returncode
            # Si le processus a été tué (timeout), returncode peut être None ou négatif
            if return_code is None:
                 # Essayer de le récupérer à nouveau après un court instant
                 time.sleep(0.1)
                 process.poll()
                 return_code = process.returncode or -1 # Assigner -1 si toujours None

            # 8. Construction des sorties complètes
            stdout = "\n".join(line.rstrip() for line in stdout_data)
            stderr = "\n".join(line.rstrip() for line in stderr_data)

            # 9. Vérification du succès et logging de la sortie non logguée
            success = (return_code == 0)

            # Logguer stdout/stderr si no_output=False et pas déjà fait par real_time (non implémenté ici)
            if not no_output:
                for line in stdout_data:
                     if line.strip(): self.log_info(line.strip())
                log_stderr_func = self.log_warning if error_as_warning else self.log_error
                for line in stderr_data:
                     if line.strip(): log_stderr_func(line.strip())

            # Gérer le cas spécifique de sudo échouant à cause du mot de passe
            if use_sudo and return_code != 0 and ("incorrect password attempt" in stderr.lower() or "sudo: a password is required" in stderr.lower()):
                 err_msg = "Échec de l'authentification sudo."
                 self.log_error(err_msg)
                 if check:
                      # Lever une exception PermissionError spécifique
                      raise PermissionError(err_msg)
                 else:
                      return False, stdout, stderr # Retourner échec

            # Gérer check=True
            if check and not success:
                 error_msg_detail = f"Commande échouée avec code {return_code}.\nStderr: {stderr}\nStdout: {stdout}"
                 self.log_error(f"Erreur lors de l'exécution de: {cmd_str_for_log}")
                 self.log_error(error_msg_detail)
                 raise subprocess.CalledProcessError(return_code, cmd_to_run, output=stdout, stderr=stderr)

            return success, stdout, stderr

        except FileNotFoundError as e:
             # Commande (ou sudo) non trouvée
             self.log_error(f"Erreur: Commande ou dépendance introuvable: {e.filename}")
             raise # Relancer pour que l'appelant sache
        except PermissionError as e:
             # Erreur de permission (souvent sudo)
             self.log_error(f"Erreur de permission: {e}")
             raise # Relancer
        except Exception as e:
             # Autres erreurs inattendues
             self.log_error(f"Erreur inattendue lors de l'exécution de {cmd_str_for_log}: {e}", exc_info=True)
             # Essayer de récupérer stdout/stderr si possible
             stdout_err = "\n".join(stdout_data)
             stderr_err = "\n".join(stderr_data)
             # Si check=True, lever l'exception originale est peut-être mieux
             if check: raise
             return False, stdout_err, stderr_err # Retourner échec si check=False
