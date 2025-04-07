# install/plugins/plugins_utils/interactive_command.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module utilitaire pour exécuter des commandes interactives via Pexpect.
Fournit une interface structurée pour définir des scénarios d'interaction.
NOTE: Nécessite l'installation du paquet pip 'pexpect'.
"""

from .plugin_utils_base import PluginUtilsBase
import sys
import time
import os
import shlex
import io # Pour capturer la sortie dans un buffer
from typing import Union, Optional, List, Dict, Any, Tuple, Sequence, Pattern

# Essayer d'importer pexpect
try:
    import pexpect
    PEXPECT_AVAILABLE = True
    # Définir les exceptions pexpect pour le type hinting et la gestion d'erreur
    PexpectError = pexpect.exceptions.ExceptionPexpect
    TIMEOUT = pexpect.exceptions.TIMEOUT
    EOF = pexpect.exceptions.EOF
except ImportError:
    PEXPECT_AVAILABLE = False
    # Définir des exceptions factices
    class PexpectError(Exception): pass
    class TIMEOUT(PexpectError): pass
    class EOF(PexpectError): pass
    class pexpect: # Factice
        TIMEOUT = TIMEOUT
        EOF = EOF
        @staticmethod
        def spawn(*args, **kwargs): raise ImportError("Le module 'pexpect' est requis.")
        # Méthode factice pour compile_pattern_list si pexpect n'est pas là
        @staticmethod
        def compile_pattern_list(patterns):
             if isinstance(patterns, list): return patterns
             return [patterns]


class InteractiveCommand(PluginUtilsBase):
    """
    Classe pour exécuter des commandes interactives via Pexpect.
    Permet de définir des scénarios d'attente/réponse.
    Hérite de PluginUtilsBase pour la journalisation.
    """

    DEFAULT_TIMEOUT = 30 # Timeout par défaut pour chaque étape d'attente en secondes

    def __init__(self, logger=None, target_ip=None):
        """Initialise le gestionnaire de commandes interactives."""
        super().__init__(logger, target_ip)
        if not PEXPECT_AVAILABLE:
            self.log_error("Le module 'pexpect' est requis mais n'a pas pu être importé. "
                           "Les opérations interactives échoueront. Installez-le via pip.")
            # Ne pas lever d'exception ici, mais les méthodes échoueront

    def run_scenario(self,
                     command: Union[str, List[str]],
                     scenario: List[Tuple[Union[str, Pattern, List[Union[str, Pattern]]], Optional[str], Optional[int]]],
                     # Format scenario: [(expect_pattern(s), response_to_send, timeout_override), ...]
                     global_timeout: int = DEFAULT_TIMEOUT,
                     log_transcript: bool = True,
                     encoding: str = 'utf-8',
                     cwd: Optional[str] = None,
                     env: Optional[Dict[str, str]] = None,
                     needs_sudo: bool = False,
                     # Le mot de passe sudo est géré par l'environnement (SUDO_PASSWORD)
                     # et la méthode run de base qui préfixe avec 'sudo -S'
                     mask_responses: Optional[List[int]] = None # Indices des réponses à masquer
                     ) -> Tuple[bool, str]:
        """
        Exécute une commande interactive en suivant un scénario d'attentes et de réponses.

        Args:
            command: Commande à exécuter (chaîne ou liste).
            scenario: Liste de tuples définissant les étapes d'interaction:
                      - expect_pattern(s): Chaîne (littérale), regex compilée, ou liste de chaînes/regex à attendre.
                                           pexpect.TIMEOUT et pexpect.EOF sont automatiquement ajoutés.
                      - response_to_send: Chaîne à envoyer après avoir trouvé le pattern (None pour ne rien envoyer).
                                          Ajoute automatiquement '\\n' à la fin (sendline).
                      - timeout_override: Timeout spécifique pour cette étape en secondes (None pour utiliser global_timeout).
            global_timeout: Timeout par défaut pour chaque attente (secondes).
            log_transcript: Si True, loggue l'intégralité de l'interaction (peut inclure des données sensibles si non masquées).
            encoding: Encodage à utiliser pour la communication.
            cwd: Répertoire de travail.
            env: Environnement d'exécution (remplace l'environnement courant si fourni).
            needs_sudo: Si True, préfixe la commande avec 'sudo -S'. Le mot de passe doit être
                        disponible via la variable d'environnement SUDO_PASSWORD (géré par l'appelant).
            mask_responses: Liste des indices (0-based) des réponses dans le scénario
                            qui doivent être masquées dans les logs (ex: mots de passe).

        Returns:
            Tuple (success: bool, full_output: str).
            'success' est True si le scénario s'est déroulé sans timeout/EOF inattendu et
            si le code de sortie final est 0.
            'full_output' contient la transcription complète de l'interaction si log_transcript=True,
            sinon une approximation basée sur ce que pexpect a lu.
        """
        if not PEXPECT_AVAILABLE:
            return False, "Module pexpect non disponible."

        # --- Préparation de la commande ---
        if isinstance(command, list):
            cmd_list = command
            # Utiliser shlex.quote pour un affichage sûr des arguments
            cmd_str_log = ' '.join(shlex.quote(c) for c in command)
        else:
            cmd_str_log = command # Logguer la commande originale
            # Tenter de découper pour pexpect.spawn, mais garder la chaîne pour le log
            try:
                 cmd_list = shlex.split(command)
            except ValueError:
                 self.log_warning(f"Impossible de découper la commande '{command}', exécution via shell peut être nécessaire si pexpect échoue.")
                 # Pexpect peut parfois gérer une chaîne directement, on essaie
                 cmd_list = command

        spawn_cmd: str
        spawn_args: List[str]
        # Hériter de l'environnement et le modifier si nécessaire
        effective_env = os.environ.copy()
        if env is not None:
             effective_env.update(env)

        if needs_sudo:
            if self._is_root:
                self.log_debug("needs_sudo=True mais déjà root, exécution directe.")
                # Utiliser la commande telle quelle
                if isinstance(cmd_list, list):
                     spawn_cmd = cmd_list[0]
                     spawn_args = cmd_list[1:]
                else:
                     spawn_cmd = cmd_list # Pexpect tentera d'exécuter la chaîne
                     spawn_args = []
            else:
                self.log_info("Préfixage de la commande avec 'sudo -S'")
                sudo_path = '/usr/bin/sudo' # Chemin commun
                # Vérifier si sudo existe (déjà fait dans PluginUtilsBase.run, mais redondance ici)
                which_success, which_out, _ = self.run(['which', 'sudo'], check=False, no_output=True)
                if which_success and which_out.strip(): sudo_path = which_out.strip()

                spawn_cmd = sudo_path
                # Passer la commande originale comme arguments à sudo -S
                if isinstance(cmd_list, list):
                     # -S lit le mdp depuis stdin (normalement géré par l'env SUDO_PASSWORD)
                     # -E préserve l'environnement si possible
                     spawn_args = ['-SE'] + cmd_list
                else:
                     # Si la commande originale était une chaîne, la passer à sh -c
                     # C'est plus complexe et potentiellement moins sûr
                     spawn_args = ['-SE', 'sh', '-c', cmd_list]

                # Vérifier si le mot de passe est dans l'environnement
                if "SUDO_PASSWORD" not in effective_env:
                     self.log_warning("sudo requis mais SUDO_PASSWORD non trouvé dans l'environnement. "
                                      "L'interaction peut échouer si un mot de passe est demandé.")
        else:
             # Exécution normale
             if isinstance(cmd_list, list):
                  spawn_cmd = cmd_list[0]
                  spawn_args = cmd_list[1:]
             else:
                  spawn_cmd = cmd_list
                  spawn_args = []

        self.log_info(f"Exécution interactive: {cmd_str_log}")

        # --- Exécution Pexpect ---
        transcript_buffer = io.StringIO() if log_transcript else None
        child: Optional[pexpect.spawn] = None
        # Stocker la sortie lue manuellement si log_transcript=False
        manual_output_log = ""

        try:
            # Démarrer le processus enfant
            # dimensions=(rows, cols) peut aider à simuler un tty plus grand si nécessaire
            child = pexpect.spawn(spawn_cmd, args=spawn_args,
                                  timeout=global_timeout, # Timeout par défaut pour les expect initiaux
                                  encoding=encoding,
                                  codec_errors='replace', # Gérer les erreurs d'encodage
                                  cwd=cwd,
                                  env=effective_env,
                                  logfile=transcript_buffer, # Capturer toute l'interaction si demandé
                                  echo=False) # Ne pas afficher l'entrée sur le tty enfant

            mask_indices = set(mask_responses or [])

            # Dérouler le scénario d'interaction
            for i, step in enumerate(scenario):
                if len(step) < 2 or len(step) > 3:
                     # Log l'erreur et continuer si possible ? Ou lever une exception ? Lever pour l'instant.
                     raise ValueError(f"Format de scénario invalide à l'étape {i+1}: {step}")

                expect_pattern_or_list = step[0]
                response_to_send = step[1]
                # Utiliser le timeout spécifique à l'étape ou le global
                step_timeout = step[2] if len(step) == 3 and step[2] is not None else global_timeout

                # Construire la liste des patterns à attendre pour cette étape
                patterns_to_expect = []
                if isinstance(expect_pattern_or_list, list):
                     patterns_to_expect.extend(expect_pattern_or_list)
                else:
                     patterns_to_expect.append(expect_pattern_or_list)

                # Ajouter les patterns spéciaux EOF et TIMEOUT
                patterns_to_expect.extend([pexpect.EOF, pexpect.TIMEOUT])
                # Compiler la liste pour pexpect (gère str, bytes, regex)
                compiled_patterns = pexpect.compile_pattern_list(patterns_to_expect)

                self.log_debug(f"  Étape {i+1}: Attente de '{expect_pattern_or_list}' (timeout={step_timeout}s)")

                # Attendre l'un des patterns
                index = child.expect(compiled_patterns, timeout=step_timeout)

                # Capturer la sortie avant et après la correspondance pour le log manuel
                output_before = child.before or ""
                output_after = child.after or ""
                if not log_transcript:
                     if output_before: manual_output_log += output_before
                     if output_after: manual_output_log += output_after
                     # Logguer ce qui a été lu (avant et le match)
                     if output_before.strip(): self.log_debug(f"    Avant: {output_before.strip()}")
                     if output_after.strip(): self.log_debug(f"    Match ({index}): {output_after.strip()}")

                matched_pattern = compiled_patterns[index] # Le pattern qui a correspondu

                # Gérer les cas spéciaux (EOF, TIMEOUT)
                if matched_pattern == pexpect.EOF:
                    # La commande s'est terminée avant la fin attendue du scénario
                    raise EOF(f"Fin de fichier inattendue à l'étape {i+1} en attendant '{expect_pattern_or_list}'.")
                elif matched_pattern == pexpect.TIMEOUT:
                    # Le prompt attendu n'est pas apparu dans le délai imparti
                    raise TIMEOUT(f"Timeout ({step_timeout}s) dépassé à l'étape {i+1} en attendant '{expect_pattern_or_list}'.")

                # Si on arrive ici, un des patterns attendus a été trouvé

                # Envoyer la réponse si définie pour cette étape
                if response_to_send is not None:
                    log_response = "********" if i in mask_indices else response_to_send
                    self.log_debug(f"    Envoi réponse: {log_response}")
                    child.sendline(response_to_send)
                    # Ajouter la réponse (masquée ou non) au log manuel si besoin
                    if not log_transcript:
                         # Ajouter un retour chariot simulé car sendline l'envoie
                         manual_output_log += log_response + "\n"

            # Fin du scénario, attendre la fin normale du processus
            self.log_debug("Fin du scénario, attente de EOF.")
            child.expect(pexpect.EOF, timeout=global_timeout)
            # Capturer le reste de la sortie
            final_before = child.before or ""
            if not log_transcript and final_before: manual_output_log += final_before
            # if not log_transcript and final_before.strip(): self.log_debug(f"    Sortie finale: {final_before.strip()}")

            child.close() # Fermer explicitement
            success = (child.exitstatus == 0)
            # Récupérer la transcription complète si logguée, sinon le log manuel
            final_output = transcript_buffer.getvalue() if log_transcript and transcript_buffer else manual_output_log

            if success:
                self.log_success(f"Commande interactive '{cmd_str_log}' terminée avec succès.")
                return True, final_output
            else:
                # Le code d'erreur est dans child.exitstatus ou child.signalstatus
                err_status = f"Exit status: {child.exitstatus}" if child.exitstatus is not None else f"Signal: {child.signalstatus}"
                self.log_error(f"Commande interactive '{cmd_str_log}' terminée avec échec. {err_status}")
                return False, final_output

        except (TIMEOUT, EOF) as e:
             # Gérer spécifiquement TIMEOUT et EOF levés par notre code ou pexpect
             self.log_error(f"Erreur d'interaction pour '{cmd_str_log}': {e}")
             partial_output = transcript_buffer.getvalue() if log_transcript and transcript_buffer else manual_output_log
             if child and not child.closed:
                  try: partial_output += child.read_nonblocking(size=1024, timeout=0.1) # Essayer de lire sans bloquer
                  except: pass
                  child.close(force=True) # Forcer la fermeture
             return False, partial_output
        except PexpectError as e:
             # Autres erreurs Pexpect (ex: échec de spawn, erreur de pattern regex)
             self.log_error(f"Erreur Pexpect pour '{cmd_str_log}': {e}", exc_info=True)
             partial_output = transcript_buffer.getvalue() if log_transcript and transcript_buffer else manual_output_log
             if child and not child.closed: child.close(force=True)
             return False, partial_output
        except Exception as e:
             # Autres erreurs inattendues
             self.log_error(f"Erreur inattendue lors de l'exécution interactive de '{cmd_str_log}': {e}", exc_info=True)
             partial_output = transcript_buffer.getvalue() if log_transcript and transcript_buffer else manual_output_log
             if child and not child.closed: child.close(force=True)
             return False, partial_output
        finally:
             # Assurer la fermeture du buffer
             if transcript_buffer: transcript_buffer.close()

