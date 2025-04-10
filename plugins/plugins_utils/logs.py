# install/plugins/plugins_utils/logs.py
#!/usr/bin/env python3
"""
Module utilitaire pour la gestion et l'analyse des fichiers journaux système.
Combine la gestion de logrotate, journald et l'analyse de contenu/taille.
Utilise logrotate, journalctl, find, du, grep, sort, uniq.
"""

from plugins_utils.plugins_utils_base import PluginsUtilsBase
import os
import re
import time
from pathlib import Path
from typing import Union, Optional, List, Dict, Any, Tuple, Generator

# Essayer d'importer ArchiveCommands si disponible
try:
    from .archive import ArchiveCommands
    ARCHIVE_AVAILABLE = True
except ImportError:
    ARCHIVE_AVAILABLE = False

class LogCommands(PluginsUtilsBase):
    """
    Classe pour la gestion et l'analyse des logs système.
    Hérite de PluginUtilsBase pour l'exécution de commandes.
    """

    DEFAULT_LOG_DIRS = ["/var/log"]
    COMMON_ERROR_PATTERNS = [
        "error", "failed", "failure", "critical", "exception", "traceback",
        "segfault", "denied", "refused", "timeout", "unable to", "cannot"
    ]

    def __init__(self, logger=None, target_ip=None):
        """Initialise le gestionnaire de logs."""
        super().__init__(logger, target_ip)
        self._archive_manager = ArchiveCommands(logger, target_ip) if ARCHIVE_AVAILABLE else None


    def check_logrotate_config(self, service_or_logpath: str) -> Optional[Dict[str, Any]]:
        """
        Vérifie la configuration logrotate pour un service ou un chemin de log.

        Args:
            service_or_logpath: Nom du service (ex: 'nginx') ou chemin du fichier log
                                (ex: '/var/log/nginx/access.log').

        Returns:
            Dictionnaire contenant les directives trouvées ou None si aucune config trouvée.
        """
        config_file = None
        logrotate_d = "/etc/logrotate.d"
        self.log_info(f"Recherche de la configuration logrotate pour: {service_or_logpath}")

        # 1. Essayer de trouver par nom de service/fichier dans /etc/logrotate.d
        if os.path.isdir(logrotate_d):
            potential_config = Path(logrotate_d) / service_or_logpath.split('/')[-1] # Utiliser le nom de base
            if potential_config.is_file():
                config_file = potential_config
            else:
                 # Essayer de trouver un fichier contenant le chemin
                 try:
                      # Utiliser grep pour chercher le chemin dans les fichiers de conf
                      cmd_grep = ['grep', '-l', '-F', service_or_logpath, f'{logrotate_d}/'] # -l: liste fichiers, -F: chaîne fixe
                      success_grep, stdout_grep, _ = self.run(cmd_grep, check=False, no_output=True, error_as_warning=True)
                      if success_grep and stdout_grep.strip():
                           # Prendre le premier fichier trouvé
                           config_file = Path(stdout_grep.strip().splitlines()[0])
                 except Exception as e_grep:
                      self.log_warning(f"Erreur lors de la recherche du fichier logrotate: {e_grep}")

        if not config_file or not config_file.is_file():
            self.log_warning(f"Aucun fichier de configuration logrotate trouvé explicitement pour '{service_or_logpath}'. "
                             "La rotation peut être gérée par /etc/logrotate.conf.")
            # On pourrait parser /etc/logrotate.conf mais c'est plus complexe
            return None

        self.log_info(f"Fichier de configuration logrotate trouvé: {config_file}")

        # 2. Parser le fichier de configuration (simpliste)
        config_data: Dict[str, Any] = {'config_file': str(config_file), 'directives': {}}
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # Extraire les directives globales ou spécifiques au logpath
                # Regex simple pour directives communes (peut être améliorée)
                pattern = re.compile(r'^\s*(\w+)\s*(.*)')
                # Chercher le bloc spécifique s'il existe
                log_block_match = re.search(r'^\s*' + re.escape(service_or_logpath) + r'\s*{([^}]*)}', content, re.MULTILINE | re.DOTALL)
                target_content = log_block_match.group(1) if log_block_match else content

                for line in target_content.splitlines():
                    match = pattern.match(line)
                    if match:
                        key = match.group(1).lower()
                        value = match.group(2).strip()
                        config_data['directives'][key] = value if value else True # Ex: 'compress' a une valeur True implicite

            self.log_debug(f"Directives logrotate trouvées: {config_data['directives']}")
            return config_data
        except Exception as e:
            self.log_error(f"Erreur lors du parsing de {config_file}: {e}")
            return None

    def force_logrotate(self, config_file: Optional[str] = None) -> bool:
        """
        Force l'exécution de logrotate. Nécessite root.

        Args:
            config_file: Chemin vers un fichier de configuration logrotate spécifique (optionnel).
                         Si None, utilise la configuration système globale.

        Returns:
            bool: True si succès.
        """
        action = f"fichier {config_file}" if config_file else "configuration globale"
        self.log_info(f"Forçage de l'exécution de logrotate pour {action}")
        cmd = ['logrotate', '-f'] # -f pour forcer
        if config_file:
            if not os.path.exists(config_file):
                 self.log_error(f"Fichier de configuration logrotate introuvable: {config_file}")
                 return False
            cmd.append(config_file)
        else:
             # Forcer pour la configuration système (/etc/logrotate.conf)
             cmd.append('/etc/logrotate.conf')

        # logrotate -f nécessite root
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)
        if stdout: self.log_info(f"Sortie logrotate:\n{stdout}") # logrotate peut être verbeux

        if success:
            self.log_success(f"Exécution forcée de logrotate réussie pour {action}.")
            return True
        else:
            self.log_error(f"Échec de l'exécution forcée de logrotate. Stderr: {stderr}")
            return False

    # --- Gestion des Fichiers Logs ---

    def list_log_files(self,
                       directories: Optional[List[str]] = None,
                       min_size_mb: Optional[float] = None,
                       older_than_days: Optional[int] = None,
                       pattern: str = "*.log*") -> List[str]:
        """
        Liste les fichiers journaux selon des critères de taille et d'âge.

        Args:
            directories: Liste de répertoires à scanner (défaut: ['/var/log']).
            min_size_mb: Taille minimale en Mo pour lister un fichier.
            older_than_days: Lister seulement les fichiers plus vieux que N jours (basé sur mtime).
            pattern: Motif de nom de fichier (glob style, ex: "*.log", "syslog*").

        Returns:
            Liste des chemins complets des fichiers trouvés.
        """
        dirs_to_scan = directories or self.DEFAULT_LOG_DIRS
        criteria_log = []
        self.log_info(f"Recherche de fichiers logs dans {', '.join(dirs_to_scan)}")
        if pattern != "*.log*": criteria_log.append(f"pattern='{pattern}'")
        if min_size_mb is not None: criteria_log.append(f"taille >= {min_size_mb} Mo")
        if older_than_days is not None: criteria_log.append(f"plus vieux que {older_than_days} jours")
        if criteria_log: self.log_info(f"  Critères: {', '.join(criteria_log)}")

        cmd = ['find'] + dirs_to_scan
        # Limiter la profondeur ? Pour l'instant non.
        # cmd.extend(['-maxdepth', '3'])
        cmd.extend(['-type', 'f']) # Seulement les fichiers
        cmd.extend(['-name', pattern]) # Filtrer par nom

        if min_size_mb is not None:
            cmd.extend(['-size', f'+{int(min_size_mb)}M'])
        if older_than_days is not None:
            cmd.extend(['-mtime', f'+{older_than_days}'])

        # find peut nécessiter root pour accéder à certains dossiers
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True, error_as_warning=True) # Ignorer erreurs de permission

        if not success and stderr and "permission denied" not in stderr.lower():
            # Erreur autre que permission denied
            self.log_error(f"Échec de la commande find. Stderr: {stderr}")
            return []
        elif stderr:
             self.log_warning(f"Erreurs de permission lors du scan des logs (normal): {stderr.splitlines()[0]}...")

        files = [line for line in stdout.splitlines() if line.strip()]
        self.log_info(f"{len(files)} fichier(s) log(s) trouvé(s) correspondant aux critères.")
        return files

    def archive_logs(self, log_files: List[str], output_archive: Union[str, Path], compression: str = 'gz') -> bool:
        """
        Crée une archive contenant les fichiers journaux spécifiés.

        Args:
            log_files: Liste des chemins complets des fichiers logs à archiver.
            output_archive: Chemin du fichier archive à créer (ex: /tmp/logs.tar.gz).
            compression: Type de compression ('gz', 'bz2', 'xz', 'zst').

        Returns:
            bool: True si l'archivage a réussi.
        """
        if not log_files:
            self.log_warning("Aucun fichier log spécifié pour l'archivage.")
            return False
        if not self._archive_manager:
            self.log_error("Le module ArchiveCommands n'est pas disponible pour créer l'archive.")
            # Fallback possible avec tar directement?
            if 'tar' not in self._cmd_paths:
                 self.log_error("Commande 'tar' non trouvée, impossible d'archiver.")
                 return False
            # Utiliser tar directement si ArchiveCommands n'est pas là
            self.log_warning("Utilisation de la commande 'tar' directe car ArchiveCommands n'est pas disponible.")
            output_path = Path(output_archive)
            cmd = ['tar']
            comp_map = {'gz': '-z', 'bz2': '-j', 'xz': '-J', 'zst': '--zstd'}
            comp_flag = comp_map.get(compression)
            if not comp_flag:
                 self.log_error(f"Type de compression tar non supporté: {compression}")
                 return False
            # c=create, f=file + compression flag
            cmd.extend([f'-c{comp_flag[1]}f' if comp_flag.startswith('-') else f'-cf {comp_flag}', str(output_path)])
            cmd.extend(log_files)
            # Archiver nécessite potentiellement root pour lire les logs
            success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)
            if success:
                 self.log_success(f"Logs archivés avec succès dans {output_path} (via tar).")
                 return True
            else:
                 self.log_error(f"Échec de l'archivage des logs via tar. Stderr: {stderr}")
                 return False
        else:
            # Utiliser ArchiveCommands
            return self._archive_manager.create_tar(output_archive, log_files, compression=compression, needs_sudo=True)

    def purge_old_logs(self,
                       directories: Optional[List[str]] = None,
                       older_than_days: int = 30,
                       pattern: str = "*.log*",
                       dry_run: bool = True) -> bool:
        """
        Supprime les fichiers journaux plus vieux qu'un certain nombre de jours.
        ATTENTION: Opération destructive ! Utiliser dry_run=False avec prudence.

        Args:
            directories: Liste de répertoires à scanner (défaut: ['/var/log']).
            older_than_days: Supprimer les fichiers plus vieux que N jours (mtime).
            pattern: Motif de nom de fichier à cibler.
            dry_run: Si True (défaut), simule seulement la suppression. Si False, supprime réellement.

        Returns:
            bool: True si l'opération (ou la simulation) a réussi.
        """
        dirs_to_scan = directories or self.DEFAULT_LOG_DIRS
        action = "Simulation de la suppression" if dry_run else "Suppression"
        self.log_warning(f"{action} des logs plus vieux que {older_than_days} jours dans {', '.join(dirs_to_scan)} (pattern: '{pattern}')")
        if not dry_run:
            self.log_warning("!!! OPÉRATION DESTRUCTIVE ACTIVÉE !!!")

        cmd = ['find'] + dirs_to_scan
        cmd.extend(['-type', 'f'])
        cmd.extend(['-name', pattern])
        cmd.extend(['-mtime', f'+{older_than_days}'])

        if dry_run:
            cmd.append('-print') # Afficher les fichiers qui seraient supprimés
        else:
            cmd.append('-delete') # Supprimer réellement

        # find -delete nécessite root
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)

        if dry_run:
            if success:
                 files_found = stdout.splitlines()
                 if files_found:
                      self.log_info(f"Simulation: {len(files_found)} fichier(s) seraient supprimé(s):")
                      for f in files_found[:10]: # Afficher les 10 premiers
                           self.log_info(f"  - {f}")
                      if len(files_found) > 10: self.log_info("  - ... et autres.")
                 else:
                      self.log_info("Simulation: Aucun fichier à supprimer trouvé.")
                 return True
            else:
                 self.log_error(f"Échec de la simulation de suppression. Stderr: {stderr}")
                 return False
        else: # Suppression réelle
            if success:
                 self.log_success(f"Vieux fichiers logs supprimés avec succès (si trouvés).")
                 # find -delete n'affiche rien en cas de succès
                 self.log_info("Utiliser 'list_log_files' pour vérifier les fichiers restants si nécessaire.")
                 return True
            else:
                 self.log_error(f"Échec de la suppression des vieux logs. Stderr: {stderr}")
                 return False

    # --- Gestion Journald ---

    def journald_vacuum_size(self, max_size_mb: int) -> bool:
        """Réduit la taille des logs journald à une taille maximale."""
        if not self._cmd_paths.get('journalctl'):
            self.log_error("Commande 'journalctl' non trouvée.")
            return False
        size_str = f"{max_size_mb}M"
        self.log_info(f"Réduction de la taille des logs journald à {size_str} (journalctl --vacuum-size)")
        cmd = [self._cmd_paths['journalctl'], f"--vacuum-size={size_str}"]
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)
        if stdout: self.log_info(f"Sortie journalctl vacuum-size:\n{stdout}")
        if success:
            self.log_success("Nettoyage journald par taille réussi.")
            return True
        else:
            self.log_error(f"Échec du nettoyage journald par taille. Stderr: {stderr}")
            return False

    def journald_vacuum_time(self, time_spec: str) -> bool:
        """Supprime les entrées journald plus anciennes qu'une date/durée."""
        if not self._cmd_paths.get('journalctl'):
            self.log_error("Commande 'journalctl' non trouvée.")
            return False
        self.log_info(f"Suppression des entrées journald antérieures à '{time_spec}' (journalctl --vacuum-time)")
        cmd = [self._cmd_paths['journalctl'], f"--vacuum-time={time_spec}"]
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)
        if stdout: self.log_info(f"Sortie journalctl vacuum-time:\n{stdout}")
        if success:
            self.log_success("Nettoyage journald par temps réussi.")
            return True
        else:
            self.log_error(f"Échec du nettoyage journald par temps. Stderr: {stderr}")
            return False

    # --- Analyse de Logs ---

    def find_large_logs(self, directories: Optional[List[str]] = None, size_threshold_mb: int = 100) -> List[Tuple[str, int]]:
        """Trouve les fichiers logs dépassant une certaine taille."""
        files_found = self.list_log_files(directories=directories, min_size_mb=size_threshold_mb, pattern="*") # Chercher tous types de fichiers
        results = []
        if files_found:
             self.log_info(f"Analyse de la taille des {len(files_found)} fichier(s) trouvé(s)...")
             # Utiliser `du -k` pour obtenir la taille réelle
             cmd_du = ['du', '-k'] + files_found
             success_du, stdout_du, stderr_du = self.run(cmd_du, check=False, no_output=True, needs_sudo=True)
             if success_du:
                  for line in stdout_du.splitlines():
                       try:
                            size_k_str, path = line.split(None, 1)
                            size_mb = int(size_k_str) / 1024
                            if size_mb >= size_threshold_mb:
                                 results.append((path.strip(), int(size_mb)))
                       except (ValueError, IndexError):
                            continue # Ignorer les lignes mal formées
                  # Trier par taille décroissante
                  results.sort(key=lambda x: x[1], reverse=True)
                  self.log_info(f"{len(results)} fichier(s) log(s) dépassant {size_threshold_mb} Mo trouvés.")
             else:
                  self.log_error(f"Impossible d'obtenir la taille via 'du'. Stderr: {stderr_du}")
        else:
             self.log_info(f"Aucun fichier trouvé dépassant {size_threshold_mb} Mo.")

        return results

    def find_frequent_lines(self, log_file: Union[str, Path], top_n: int = 10, patterns_to_ignore: Optional[List[str]] = None) -> List[Tuple[int, str]]:
        """
        Identifie les lignes les plus fréquentes dans un fichier log.

        Args:
            log_file: Chemin du fichier log.
            top_n: Nombre de lignes les plus fréquentes à retourner.
            patterns_to_ignore: Liste d'expressions régulières pour ignorer certaines lignes.

        Returns:
            Liste de tuples (count, line) triée par fréquence décroissante.
        """
        log_path = Path(log_file)
        if not log_path.is_file():
            self.log_error(f"Fichier log introuvable: {log_path}")
            return []

        self.log_info(f"Recherche des {top_n} lignes les plus fréquentes dans {log_path}")
        # Construire la commande pipeline: cat | grep -vE (ignore) | sort | uniq -c | sort -nr | head -n N
        # Note: 'cat' n'est pas idéal pour gros fichiers, mais simple pour le pipeline.
        #       Alternative: traiter en Python (plus lent mais moins de mémoire si très gros fichier).
        #       On reste sur les commandes pour la cohérence.

        cmd_parts = [f"cat {shlex.quote(str(log_path))}"]

        # Ajouter grep pour ignorer des patterns si nécessaire
        if patterns_to_ignore:
            grep_opts = " ".join(f"-e {shlex.quote(p)}" for p in patterns_to_ignore)
            cmd_parts.append(f"grep -vE {grep_opts}")

        cmd_parts.extend([
            "sort",
            "uniq -c",
            "sort -nr", # Trier numériquement et inversement
            f"head -n {top_n}"
        ])

        cmd_str = " | ".join(cmd_parts)
        self.log_debug(f"Exécution pipeline: {cmd_str}")

        # Exécuter via shell
        success, stdout, stderr = self.run(cmd_str, shell=True, check=False, no_output=True, needs_sudo=True) # Lire le log peut nécessiter sudo

        if not success:
            self.log_error(f"Échec de l'analyse des lignes fréquentes. Stderr: {stderr}")
            return []

        results = []
        # Format sortie: "  COUNT LINE"
        pattern = re.compile(r'^\s*(\d+)\s+(.*)$')
        for line in stdout.splitlines():
            match = pattern.match(line)
            if match:
                try:
                    count = int(match.group(1))
                    log_line = match.group(2)
                    results.append((count, log_line))
                except ValueError:
                    self.log_warning(f"Impossible de parser la ligne fréquente: {line}")

        self.log_info(f"{len(results)} ligne(s) fréquente(s) identifiée(s).")
        return results

    def search_log_errors(self,
                          log_file: Union[str, Path],
                          error_patterns: Optional[List[str]] = None,
                          time_since: Optional[str] = None, # Ex: '1 hour ago', 'yesterday'
                          max_lines: int = 100) -> List[str]:
        """
        Recherche des erreurs ou motifs spécifiques dans un fichier log ou journald.

        Args:
            log_file: Chemin du fichier log OU 'journald' pour chercher dans le journal systemd.
            error_patterns: Liste d'expressions régulières à rechercher. Si None, utilise COMMON_ERROR_PATTERNS.
            time_since: Ne chercher que les entrées depuis ce moment (format 'journalctl --since').
                        Uniquement applicable si log_file='journald'.
            max_lines: Nombre maximum de lignes d'erreur à retourner.

        Returns:
            Liste des lignes contenant les erreurs trouvées.
        """
        target = str(log_file)
        is_journald = (target.lower() == 'journald')
        self.log_info(f"Recherche d'erreurs dans: {target}")

        patterns = error_patterns or self.COMMON_ERROR_PATTERNS
        if not patterns:
            self.log_warning("Aucun motif d'erreur spécifié pour la recherche.")
            return []

        # Construire l'expression régulière combinée: '(pattern1|pattern2|...)'
        regex = '|'.join(f"({p})" for p in patterns)
        self.log_debug(f"Utilisation du pattern regex: {regex[:100]}...")

        if is_journald:
            if not self._cmd_paths.get('journalctl'):
                 self.log_error("Commande 'journalctl' non trouvée.")
                 return []
            cmd = [self._cmd_paths['journalctl'], '--no-pager', '-p', 'err..alert'] # Priorité erreur ou plus critique
            if time_since:
                 cmd.extend(['--since', time_since])
            # Ajouter le grep pour les motifs spécifiques si fournis (journalctl -g n'est pas regex standard)
            if error_patterns: # Seulement si des patterns spécifiques sont donnés
                 cmd_str = " ".join(shlex.quote(c) for c in cmd) + f" | grep -E {shlex.quote(regex)}"
                 final_cmd: Union[str, List[str]] = cmd_str
                 use_shell = True
            else:
                 final_cmd = cmd
                 use_shell = False
        else:
            log_path = Path(target)
            if not log_path.is_file():
                self.log_error(f"Fichier log introuvable: {log_path}")
                return []
            # Utiliser grep -E pour la recherche regex
            cmd = ['grep', '-E', '-i', regex, str(log_path)] # -i pour ignorer la casse
            final_cmd = cmd
            use_shell = False

        # Limiter la sortie avec head
        if max_lines > 0:
            head_cmd = f"head -n {max_lines}"
            if use_shell:
                 final_cmd = f"{final_cmd} | {head_cmd}"
            else:
                 # Utiliser un pipe explicite si pas déjà en shell
                 cmd_str = " ".join(shlex.quote(c) for c in final_cmd)
                 final_cmd = f"{cmd_str} | {head_cmd}"
                 use_shell = True

        self.log_debug(f"Exécution recherche erreurs: {final_cmd if isinstance(final_cmd, str) else ' '.join(final_cmd)}")
        # La lecture de logs peut nécessiter sudo
        success, stdout, stderr = self.run(final_cmd, shell=use_shell, check=False, no_output=True, needs_sudo=True)

        if not success and stderr:
            # Ignorer l'erreur si grep ne trouve rien (code retour 1)
            if not (isinstance(final_cmd, str) and 'grep' in final_cmd and process.returncode == 1):
                 self.log_error(f"Échec de la recherche d'erreurs. Stderr: {stderr}")
                 return []

        lines = stdout.splitlines()
        self.log_info(f"{len(lines)} ligne(s) d'erreur trouvée(s) dans {target}.")
        return lines

