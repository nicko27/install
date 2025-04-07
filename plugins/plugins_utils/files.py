# install/plugins/plugins_utils/files.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module utilitaire pour la gestion des fichiers et répertoires.
Fournit des opérations de copie et de déplacement avec suivi de progression.
"""

import os
import shutil
import time
import fnmatch # Pour les motifs d'exclusion
from pathlib import Path
from typing import Union, Optional, List, Tuple, Dict, Any, Generator

# Import de la classe de base
from .plugin_utils_base import PluginUtilsBase

class Files(PluginUtilsBase):
    """
    Classe utilitaire pour la gestion des fichiers et répertoires.
    Hérite de PluginUtilsBase pour l'exécution de commandes (si nécessaire) et la progression.
    Utilise principalement les modules standard 'os', 'shutil', 'pathlib'.
    """

    DEFAULT_CHUNK_SIZE = 1024 * 1024 # 1 Mo pour la copie de fichiers

    def __init__(self, logger=None, target_ip=None):
        """Initialise le gestionnaire de fichiers."""
        super().__init__(logger, target_ip)
        # Vérifier les commandes si on en utilise (ex: pour les permissions via run)
        self._check_commands()

    def _check_commands(self):
        """Vérifie si les commandes externes utilisées sont disponibles."""
        # Exemples: 'cp', 'mv', 'chmod', 'chown' si on les utilise via self.run
        cmds = ['cp', 'mv', 'chmod', 'chown', 'mkdir', 'test', 'stat']
        missing = []
        for cmd in cmds:
            success, _, _ = self.run(['which', cmd], check=False, no_output=True, error_as_warning=True)
            if not success:
                missing.append(cmd)
        if missing:
            self.log_warning(f"Commandes potentiellement manquantes pour Files: {', '.join(missing)}. "
                             f"Installer 'coreutils'.")

    def get_file_size(self, path: Union[str, Path]) -> int:
        """
        Retourne la taille d'un fichier en octets via `os.path.getsize`.

        Args:
            path: Chemin vers le fichier.

        Returns:
            int: Taille en octets, ou -1 en cas d'erreur (fichier non trouvé, etc.).
        """
        file_path = Path(path)
        self.log_debug(f"Récupération de la taille du fichier: {file_path}")
        try:
            # Vérifier l'existence d'abord
            if not file_path.is_file():
                 # Essayer avec sudo si problème de permission ? Non, getsize ne marche pas via sudo run
                 self.log_error(f"Le chemin n'est pas un fichier valide ou n'existe pas: {file_path}")
                 return -1
            size = os.path.getsize(file_path)
            self.log_debug(f"Taille du fichier {file_path}: {size} octets")
            return size
        except FileNotFoundError:
            self.log_error(f"Fichier non trouvé: {file_path}")
            return -1
        except OSError as e:
             self.log_error(f"Erreur d'accès au fichier {file_path} pour getsize: {e}")
             return -1
        except Exception as e:
            self.log_error(f"Erreur inattendue lors de la lecture de la taille du fichier {file_path}: {e}", exc_info=True)
            return -1

    def get_dir_size(self, path: Union[str, Path], follow_symlinks: bool = False) -> int:
        """
        Calcule la taille totale d'un dossier en octets (récursivement) via `os.walk`.

        Args:
            path: Chemin vers le dossier.
            follow_symlinks: Si True, suit les liens symboliques (peut être dangereux).

        Returns:
            int: Taille totale en octets, ou -1 en cas d'erreur majeure.
                 Les erreurs d'accès à des fichiers individuels sont logguées mais ignorées.
        """
        dir_path = Path(path)
        self.log_info(f"Calcul de la taille du dossier: {dir_path} (follow_symlinks={follow_symlinks})")
        if not dir_path.is_dir():
             self.log_error(f"Le chemin n'est pas un dossier valide: {dir_path}")
             return -1

        total_size = 0
        items_processed = 0
        errors_encountered = 0
        # Estimer le nombre total d'items pour la progression ? Trop coûteux.
        # On va juste logguer tous les N items.
        log_interval = 1000

        try:
            for dirpath, dirnames, filenames in os.walk(str(dir_path), topdown=True, followlinks=follow_symlinks, onerror=self.log_warning):
                # Traiter les fichiers
                for f in filenames:
                    items_processed += 1
                    fp = os.path.join(dirpath, f)
                    # Ne pas suivre les liens si follow_symlinks est False
                    if not follow_symlinks and os.path.islink(fp):
                        continue
                    try:
                        total_size += os.path.getsize(fp)
                    except OSError as e:
                         # Logguer seulement les erreurs pertinentes (Permission denied, etc.)
                         # FileNotFoundError peut arriver si fichier supprimé pendant le scan
                         if e.errno != 2: # errno 2 = No such file or directory
                              self.log_warning(f"Erreur d'accès au fichier {fp} pendant calcul taille: {e}")
                              errors_encountered += 1
                         continue # Ignorer les fichiers inaccessibles/disparus

                    if items_processed % log_interval == 0:
                         self.log_debug(f"  ... {items_processed} éléments scannés, taille actuelle: {total_size / (1024*1024):.2f} Mo")


                # Si on ne suit pas les liens, exclure les répertoires qui sont des liens
                if not follow_symlinks:
                    # Modifier dirnames in-place pour que os.walk ne les parcoure pas
                    original_dirs = list(dirnames) # Copier avant modification
                    dirnames[:] = [] # Vider la liste originale
                    for d in original_dirs:
                         dp = os.path.join(dirpath, d)
                         if not os.path.islink(dp):
                              dirnames.append(d)
                         else:
                              items_processed += 1 # Compter le lien comme un item scanné

            self.log_info(f"Taille totale calculée pour {dir_path}: {total_size / (1024*1024):.2f} Mo ({total_size} octets)")
            if errors_encountered > 0:
                 self.log_warning(f"{errors_encountered} erreur(s) d'accès rencontrée(s) pendant le calcul.")
            return total_size
        except Exception as e:
            self.log_error(f"Erreur majeure lors du calcul de la taille du dossier {dir_path}: {e}", exc_info=True)
            return -1

    def _copy_file_with_progress(self, src: Path, dst: Path, total_size: int, task_id: str, chunk_size: int = DEFAULT_CHUNK_SIZE):
        """Copie un seul fichier avec mise à jour de la progression (interne)."""
        copied_bytes = 0
        src_filename = src.name
        last_update_time = time.monotonic()
        update_interval = 0.5 # Mettre à jour max toutes les 0.5 secondes

        try:
            with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
                while True:
                    chunk = fsrc.read(chunk_size)
                    if not chunk:
                        break
                    fdst.write(chunk)
                    copied_bytes += len(chunk)
                    current_time = time.monotonic()

                    # Mettre à jour la progression périodiquement ou à la fin
                    if current_time - last_update_time >= update_interval or copied_bytes == total_size:
                        progress_percent = (copied_bytes / total_size) * 100 if total_size > 0 else 100
                        current_step = int(progress_percent) # Barre de 0 à 100
                        # Afficher en Mo pour lisibilité
                        copied_mb = copied_bytes / (1024 * 1024)
                        total_mb = total_size / (1024 * 1024)
                        # Utiliser update_bar directement
                        if self.use_visual_bars:
                             self.logger.update_bar(task_id, current_step, 100,
                                                    pre_text=f"Copie {src_filename}",
                                                    post_text=f"{copied_mb:.1f}/{total_mb:.1f} Mo")
                        # Mettre à jour aussi la progression numérique interne
                        self.logger.next_step(task_id, current_step=current_step)
                        last_update_time = current_time

        except Exception as e:
             self.log_error(f"Erreur pendant la copie de {src} vers {dst}: {e}")
             raise # Relancer pour que l'appelant gère

    def copy_file(self, src: Union[str, Path], dst: Union[str, Path],
                  chunk_size: int = DEFAULT_CHUNK_SIZE, task_id: Optional[str] = None) -> bool:
        """
        Copie un fichier avec une barre de progression basée sur la taille.
        Préserve les métadonnées (permissions, timestamps) via `shutil.copystat`.

        Args:
            src: Chemin source.
            dst: Chemin destination (peut être un dossier, le nom de fichier sera préservé).
            chunk_size: Taille des chunks pour la copie et la mise à jour de la progression.
            task_id: ID de tâche pour la progression (optionnel).

        Returns:
            bool: True si la copie a réussi.
        """
        src_path = Path(src)
        dst_path = Path(dst)

        # Vérifier la source
        if not src_path.is_file():
            self.log_error(f"Source n'est pas un fichier valide: {src}")
            return False

        # Déterminer le chemin de destination final
        if dst_path.is_dir():
            final_dst = dst_path / src_path.name
        else:
            final_dst = dst_path
            # Créer le dossier parent si nécessaire (peut nécessiter sudo)
            self.log_debug(f"Vérification/Création du dossier parent: {final_dst.parent}")
            try:
                # Utiliser mkdir via self.run pour gérer sudo
                success_mkdir, _, err_mkdir = self.run(['mkdir', '-p', str(final_dst.parent)], check=False, needs_sudo=True)
                if not success_mkdir:
                     self.log_error(f"Impossible de créer le dossier parent {final_dst.parent}. Stderr: {err_mkdir}")
                     return False
            except Exception as e:
                self.log_error(f"Erreur lors de la création de {final_dst.parent}: {e}", exc_info=True)
                return False

        # Obtenir la taille pour la progression
        total_size = self.get_file_size(src_path)
        if total_size < 0:
            return False # Erreur déjà logguée par get_file_size

        current_task_id = task_id or f"copy_file_{src_path.name}_{int(time.time())}"
        total_mb = total_size / (1024 * 1024)
        self.log_info(f"Copie de {src_path} vers {final_dst} ({total_mb:.2f} Mo)")

        # Démarrer la tâche avec 100 étapes (pourcentage)
        self.start_task(100, description=f"Copie {src_path.name}", task_id=current_task_id)

        try:
            # Copier le fichier avec progression
            # Note: La copie elle-même n'utilise pas sudo, mais la lecture/écriture peut échouer
            # si les permissions sont insuffisantes. L'appelant doit s'assurer des droits.
            self._copy_file_with_progress(src_path, final_dst, total_size, current_task_id, chunk_size)

            # Copier les métadonnées (permissions, timestamps)
            # shutil.copystat peut échouer si pas les droits, utiliser chown/chmod via self.run ?
            try:
                shutil.copystat(src_path, final_dst)
            except OSError as e_stat:
                 self.log_warning(f"Impossible de copier les métadonnées de {src_path} vers {final_dst}: {e_stat}")
                 # Essayer de définir des permissions basiques si la copie stat échoue ?

            self.log_success(f"Fichier copié avec succès: {final_dst}")
            self.complete_task(success=True)
            return True
        except Exception as e:
            self.log_error(f"Erreur lors de la copie de {src_path} vers {final_dst}: {e}", exc_info=True)
            self.complete_task(success=False, message="Erreur copie fichier")
            # Essayer de supprimer le fichier partiellement copié
            if final_dst.exists():
                try: final_dst.unlink()
                except: pass
            return False

    def _list_files_recursive(self, src_path: Path, exclude_patterns: Optional[List[str]] = None) -> Generator[Tuple[Path, Path], None, None]:
        """Générateur listant les fichiers à copier/déplacer (chemin relatif, chemin absolu)."""
        exclude_set = set(exclude_patterns or [])
        for root, dirs, files in os.walk(str(src_path), topdown=True, onerror=self.log_warning):
            root_path = Path(root)
            rel_root_path = root_path.relative_to(src_path)

            # Filtrer les répertoires exclus
            original_dirs = list(dirs) # Copier avant modification
            dirs[:] = [] # Vider la liste originale
            for d in original_dirs:
                 dir_rel_path_str = (rel_root_path / d).as_posix() # Chemin relatif pour comparaison
                 # Vérifier si le chemin exact ou un motif correspond
                 is_excluded = dir_rel_path_str in exclude_set or \
                               any(fnmatch.fnmatch(dir_rel_path_str, pat) for pat in exclude_set)
                 if not is_excluded:
                      dirs.append(d) # Garder le dossier s'il n'est pas exclu

            # Générer les fichiers du répertoire courant (non exclus)
            for name in files:
                rel_path = rel_root_path / name
                abs_path = root_path / name
                rel_path_str = rel_path.as_posix()
                # Vérifier les exclusions pour les fichiers
                is_excluded = rel_path_str in exclude_set or \
                              any(fnmatch.fnmatch(rel_path_str, pat) for pat in exclude_set)
                if not is_excluded:
                    yield rel_path, abs_path # Retourner chemin relatif et absolu

    def copy_dir(self, src: Union[str, Path], dst: Union[str, Path],
                 exclude_patterns: Optional[List[str]] = None, task_id: Optional[str] = None) -> bool:
        """
        Copie un répertoire récursivement via `shutil.copy2` avec progression basée sur le nombre de fichiers.
        Préserve les métadonnées.

        Args:
            src: Dossier source.
            dst: Dossier destination.
            exclude_patterns: Liste de chemins relatifs (depuis src) ou motifs glob (style fnmatch) à exclure.
            task_id: ID de tâche pour la progression (optionnel).

        Returns:
            bool: True si la copie a réussi.
        """
        src_path = Path(src)
        dst_path = Path(dst)

        if not src_path.is_dir():
            self.log_error(f"Source n'est pas un dossier valide: {src}")
            return False

        current_task_id = task_id or f"copy_dir_{src_path.name}_{int(time.time())}"
        self.log_info(f"Copie du dossier {src_path} vers {dst_path}")
        if exclude_patterns:
             self.log_info(f"  Exclusions: {exclude_patterns}")

        # 1. Lister tous les fichiers à copier pour compter le total
        try:
            files_to_copy = list(self._list_files_recursive(src_path, exclude_patterns))
            total_files = len(files_to_copy)
            if total_files == 0:
                 self.log_info("Aucun fichier à copier dans le dossier source (ou tout est exclu).")
                 # Créer le dossier destination s'il n'existe pas (peut nécessiter sudo)
                 self.run(['mkdir', '-p', str(dst_path)], check=False, needs_sudo=True)
                 return True
        except Exception as e:
             self.log_error(f"Erreur lors du listage des fichiers dans {src_path}: {e}", exc_info=True)
             return False

        self.log_info(f"Environ {total_files} fichier(s) à copier.")
        self.start_task(total_files, description=f"Copie dossier {src_path.name}", task_id=current_task_id)

        # 2. Copier les fichiers
        copied_count = 0
        try:
            # Créer le dossier destination principal (peut nécessiter sudo)
            self.run(['mkdir', '-p', str(dst_path)], check=False, needs_sudo=True)

            for rel_path, abs_src_path in files_to_copy:
                abs_dst_path = dst_path / rel_path
                # Créer le sous-dossier parent dans la destination si nécessaire (peut nécessiter sudo)
                if not abs_dst_path.parent.exists():
                     self.run(['mkdir', '-p', str(abs_dst_path.parent)], check=False, needs_sudo=True)

                # Copier le fichier via shutil (peut échouer si pas les droits)
                # Pourrait utiliser `cp -a` via self.run pour gérer sudo ?
                # Essayons shutil d'abord, puis fallback cp ? Non, trop complexe.
                # L'appelant doit s'assurer que le processus a les droits ou utiliser un plugin sudo.
                try:
                    shutil.copy2(abs_src_path, abs_dst_path, follow_symlinks=False) # copy2 préserve métadonnées, ne pas suivre les liens ici
                except (IOError, OSError) as e_copy:
                     # Si shutil échoue, logguer et continuer ou arrêter ? Arrêter.
                     self.log_error(f"Échec de la copie de {abs_src_path} vers {abs_dst_path}: {e_copy}")
                     raise # Remonter l'erreur

                copied_count += 1
                # Mettre à jour la progression tous les N fichiers pour éviter trop de logs/updates
                if copied_count % 10 == 0 or copied_count == total_files:
                     self.update_task(advance=10 if copied_count % 10 == 0 else total_files % 10,
                                      description=f"Copie {rel_path}")

            # Assurer que la progression atteint 100%
            self.update_task(advance=0) # Pour forcer la mise à jour finale si besoin
            self.log_success(f"Dossier {src_path} copié avec succès vers {dst_path} ({copied_count} fichiers).")
            self.complete_task(success=True)
            return True

        except Exception as e:
            self.log_error(f"Erreur lors de la copie du dossier {src_path}: {e}", exc_info=True)
            self.complete_task(success=False, message="Erreur copie dossier")
            return False

    def move_file(self, src: Union[str, Path], dst: Union[str, Path], task_id: Optional[str] = None) -> bool:
        """
        Déplace un fichier. Tente d'abord un renommage atomique (`os.rename`),
        sinon effectue une copie (avec progression) puis supprime la source.

        Args:
            src: Chemin source.
            dst: Chemin destination (peut être un dossier).
            task_id: ID de tâche pour la progression (utilisé si copie nécessaire).

        Returns:
            bool: True si le déplacement a réussi.
        """
        src_path = Path(src)
        dst_path = Path(dst)
        current_task_id = task_id or f"move_file_{src_path.name}_{int(time.time())}"

        if not src_path.is_file():
            self.log_error(f"Source n'est pas un fichier valide: {src}")
            return False

        # Déterminer la destination finale
        if dst_path.is_dir():
            final_dst = dst_path / src_path.name
        else:
            final_dst = dst_path

        self.log_info(f"Déplacement de {src_path} vers {final_dst}")

        try:
            # Créer le dossier parent destination si nécessaire (peut nécessiter sudo)
            if not final_dst.parent.exists():
                 self.run(['mkdir', '-p', str(final_dst.parent)], check=False, needs_sudo=True)

            # Essayer d'abord un renommage (rapide si même système de fichiers)
            try:
                # os.rename peut nécessiter sudo si on déplace vers/depuis dossier protégé
                # Difficile à gérer proprement. On suppose que l'utilisateur a les droits
                # ou que le déplacement se fait dans des zones accessibles.
                # Alternative: utiliser `mv` via self.run ?
                os.rename(src_path, final_dst)
                self.log_success(f"Fichier déplacé avec succès (renommage): {final_dst}")
                return True
            except OSError as e_rename:
                # Si le renommage échoue (ex: cross-device link, permissions), copier puis supprimer
                self.log_info(f"Renommage impossible ({e_rename}), tentative de copie puis suppression...")
                # Utiliser la fonction de copie avec progression
                copy_success = self.copy_file(src_path, final_dst, task_id=current_task_id)

                if copy_success:
                    # Supprimer la source si la copie a réussi
                    try:
                        src_path.unlink() # Peut échouer si pas les droits
                        self.log_success(f"Fichier déplacé avec succès (copie+suppression): {final_dst}")
                        return True
                    except Exception as e_unlink:
                        self.log_error(f"Copie réussie vers {final_dst} mais échec de la suppression de la source {src_path}: {e_unlink}")
                        return False # Considérer comme un échec car la source reste
                else:
                    # La copie a échoué
                    self.log_error(f"Échec de la copie lors du déplacement de {src_path}")
                    return False

        except Exception as e:
            self.log_error(f"Erreur lors du déplacement de {src_path}: {e}", exc_info=True)
            return False

    def move_dir(self, src: Union[str, Path], dst: Union[str, Path],
                 exclude_patterns: Optional[List[str]] = None, task_id: Optional[str] = None) -> bool:
        """
        Déplace un dossier. Tente d'abord un renommage (`os.rename`),
        sinon effectue une copie récursive (avec progression) puis supprime la source (`shutil.rmtree`).

        Args:
            src: Dossier source.
            dst: Dossier destination.
            exclude_patterns: Liste de chemins relatifs ou motifs glob à exclure si une copie est nécessaire.
            task_id: ID de tâche pour la progression (utilisé si copie nécessaire).

        Returns:
            bool: True si le déplacement a réussi.
        """
        src_path = Path(src)
        dst_path = Path(dst)
        current_task_id = task_id or f"move_dir_{src_path.name}_{int(time.time())}"

        if not src_path.is_dir():
            self.log_error(f"Source n'est pas un dossier valide: {src}")
            return False

        # La destination ne doit pas exister pour un renommage de dossier
        if dst_path.exists():
             # Si c'est un dossier et qu'il est vide, on pourrait le supprimer ? Non, trop risqué.
             # Si c'est un fichier, erreur.
             # Si c'est un dossier non vide, erreur.
             # Le renommage échouera de toute façon si dst existe.
             self.log_debug(f"Le chemin destination {dst_path} existe déjà.")


        self.log_info(f"Déplacement du dossier {src_path} vers {dst_path}")

        try:
            # Créer le dossier parent destination si nécessaire
            if not dst_path.parent.exists():
                 self.run(['mkdir', '-p', str(dst_path.parent)], check=False, needs_sudo=True)

            # Essayer d'abord un renommage
            try:
                # os.rename pour dossiers nécessite que dst n'existe pas
                os.rename(src_path, dst_path)
                self.log_success(f"Dossier déplacé avec succès (renommage): {dst_path}")
                return True
            except OSError as e_rename:
                # Si le renommage échoue (cross-device, dst existe, permissions), copier puis supprimer
                self.log_info(f"Renommage impossible ({e_rename}), tentative de copie puis suppression...")
                # Utiliser la fonction de copie avec progression
                copy_success = self.copy_dir(src_path, dst_path, exclude_patterns, task_id=current_task_id)

                if copy_success:
                    # Supprimer la source si la copie a réussi
                    try:
                        # shutil.rmtree peut nécessiter sudo
                        # Utiliser `rm -rf` via self.run est plus cohérent pour sudo
                        cmd_rm = ['rm', '-rf', str(src_path)]
                        success_rm, _, stderr_rm = self.run(cmd_rm, check=False, needs_sudo=True)
                        if not success_rm:
                             raise OSError(f"Échec de rm -rf {src_path}: {stderr_rm}")

                        self.log_success(f"Dossier déplacé avec succès (copie+suppression): {dst_path}")
                        return True
                    except Exception as e_rmtree:
                        self.log_error(f"Copie réussie vers {dst_path} mais échec de la suppression de la source {src_path}: {e_rmtree}")
                        return False # Échec car la source reste
                else:
                    # La copie a échoué
                    self.log_error(f"Échec de la copie lors du déplacement de {src_path}")
                    return False

        except Exception as e:
            self.log_error(f"Erreur lors du déplacement du dossier {src_path}: {e}", exc_info=True)
            return False
