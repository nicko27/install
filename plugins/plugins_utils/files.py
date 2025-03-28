#!/usr/bin/env python3
"""
Module utilitaire pour la gestion des fichiers.
Fournit une classe Files de base pour gérer les opérations sur les fichiers
avec une gestion appropriée des erreurs, des logs et des barres de progression.
"""

import os
import shutil
from pathlib import Path
from typing import Union, Optional, List, Tuple

class Files:
    """
    Classe utilitaire pour la gestion des fichiers.
    Permet de gérer les opérations sur les fichiers avec une gestion appropriée des logs et des erreurs.
    """

    def __init__(self, logger=None):
        """
        Initialise un gestionnaire de fichiers.

        Args:
            logger: Instance de PluginLogger à utiliser pour la journalisation (optionnel)
        """
        self.logger = logger

        # Variables pour la gestion de la progression
        self.total_steps = 1
        self.current_step = 0

        # Si aucun logger n'est fourni, essayer d'en créer un temporaire
        if self.logger is None:
            try:
                from .pluginlogger import PluginLogger
                self.logger = PluginLogger()
            except:
                # Fallback si impossible de créer un logger
                pass

    def set_total_steps(self, total):
        """
        Définit le nombre total d'étapes pour calculer les pourcentages.

        Args:
            total: Nombre total d'étapes
        """
        self.total_steps = max(1, total)
        self.current_step = 0

        if self.logger:
            self.logger.set_total_steps(self.total_steps)

    def next_step(self, message=None):
        """
        Passe à l'étape suivante et met à jour la progression.

        Args:
            message: Message optionnel à afficher

        Returns:
            int: Étape actuelle
        """
        self.current_step += 1
        current = min(self.current_step, self.total_steps)

        # Mise à jour de la progression
        if self.logger:
            self.logger.next_step()
            if message:
                self.logger.info(message)
        else:
            progress = int(current / self.total_steps * 100)
            print(f"[PROGRESSION] {progress}% ({current}/{self.total_steps})")
            if message:
                print(f"[INFO] {message}")

        return current

    def update_progress(self, percentage, message=None):
        """
        Met à jour la progression sans passer à l'étape suivante.
        Utile pour les opérations longues avec progression continue.

        Args:
            percentage: Pourcentage de progression (0.0 à 1.0)
            message: Message optionnel à afficher
        """
        if self.logger:
            self.logger.update_progress(percentage)
            if message:
                self.logger.info(message)
        else:
            progress = int(percentage * 100)
            print(f"[PROGRESSION] {progress}%")
            if message:
                print(f"[INFO] {message}")

    def log_info(self, msg):
        """Enregistre un message d'information."""
        if self.logger:
            self.logger.info(msg)
        else:
            print(f"[LOG] [INFO] {msg}")

    def log_warning(self, msg):
        """Enregistre un message d'avertissement."""
        if self.logger:
            self.logger.warning(msg)
        else:
            print(f"[LOG] [WARNING] {msg}")

    def log_error(self, msg):
        """Enregistre un message d'erreur."""
        if self.logger:
            self.logger.error(msg)
        else:
            print(f"[LOG] [ERROR] {msg}")

    def log_debug(self, msg):
        """Enregistre un message de débogage."""
        if self.logger:
            self.logger.debug(msg)
        else:
            print(f"[LOG] [DEBUG] {msg}")

    def log_success(self, msg):
        """Enregistre un message de succès."""
        if self.logger:
            self.logger.success(msg)
        else:
            print(f"[LOG] [SUCCESS] {msg}")

    def get_file_size(self, path: Union[str, Path]) -> int:
        """
        Retourne la taille d'un fichier en octets.
        
        Args:
            path: Chemin vers le fichier
            
        Returns:
            int: Taille en octets
        """
        try:
            size = os.path.getsize(path)
            self.log_debug(f"Taille du fichier {path}: {size} octets")
            return size
        except Exception as e:
            self.log_error(f"Erreur lors de la lecture de la taille du fichier {path}: {e}")
            return 0

    def get_dir_size(self, path: Union[str, Path]) -> int:
        """
        Calcule la taille totale d'un dossier en octets.
        
        Args:
            path: Chemin vers le dossier
            
        Returns:
            int: Taille totale en octets
        """
        try:
            total = 0
            for dirpath, _, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp):
                        total += os.path.getsize(fp)
            
            self.log_debug(f"Taille du dossier {path}: {total} octets")
            return total
        except Exception as e:
            self.log_error(f"Erreur lors du calcul de la taille du dossier {path}: {e}")
            return 0

    def copy_file(self, src: Union[str, Path], dst: Union[str, Path], 
                  chunk_size: int = 1024*1024) -> Tuple[bool, str]:
        """
        Copie un fichier avec une barre de progression.
        
        Args:
            src: Chemin source
            dst: Chemin destination
            chunk_size: Taille des chunks en octets
            
        Returns:
            Tuple (success, message)
        """
        try:
            # Créer le dossier destination si nécessaire
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            
            # Obtenir la taille totale
            total_size = self.get_file_size(src)
            if total_size == 0:
                return False, "Impossible de lire la taille du fichier source"
            
            # Configurer la progression
            chunks = (total_size + chunk_size - 1) // chunk_size
            self.set_total_steps(chunks)
            self.log_info(f"Copie de {os.path.basename(src)}")
            
            # Copier par chunks avec progression
            with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
                copied = 0
                while True:
                    chunk = fsrc.read(chunk_size)
                    if not chunk:
                        break
                    fdst.write(chunk)
                    copied += len(chunk)
                    self.next_step()
            
            self.log_success(f"Fichier copié avec succès: {dst}")
            return True, "Copie réussie"
            
        except Exception as e:
            error_msg = f"Erreur lors de la copie de {src} vers {dst}: {e}"
            self.log_error(error_msg)
            return False, error_msg

    def copy_dir(self, src: Union[str, Path], dst: Union[str, Path],
                 exclude: Optional[List[str]] = None) -> Tuple[bool, str]:
        """
        Copie un dossier avec une barre de progression.
        
        Args:
            src: Dossier source
            dst: Dossier destination
            exclude: Liste de patterns à exclure (glob)
            
        Returns:
            Tuple (success, message)
        """
        try:
            # Convertir en Path pour faciliter la manipulation
            src_path = Path(src)
            dst_path = Path(dst)
            
            # Créer une liste des fichiers à copier (en excluant les patterns)
            files_to_copy = []
            for root, _, files in os.walk(src_path):
                rel_path = Path(root).relative_to(src_path)
                for file in files:
                    file_path = Path(root) / file
                    # Vérifier si le fichier doit être exclu
                    if exclude:
                        skip = False
                        for pattern in exclude:
                            if file_path.match(pattern):
                                skip = True
                                break
                        if skip:
                            continue
                    files_to_copy.append((file_path, dst_path / rel_path / file))
            
            # Configurer la progression
            self.set_total_steps(len(files_to_copy))
            self.log_info(f"Copie du dossier {os.path.basename(src)}")
            
            # Copier chaque fichier
            for src_file, dst_file in files_to_copy:
                # Créer le dossier destination si nécessaire
                os.makedirs(dst_file.parent, exist_ok=True)
                
                # Copier le fichier
                shutil.copy2(src_file, dst_file)
                self.next_step(f"Copie de {src_file.name}")
            
            self.log_success(f"Dossier copié avec succès: {dst}")
            return True, "Copie réussie"
            
        except Exception as e:
            error_msg = f"Erreur lors de la copie du dossier {src} vers {dst}: {e}"
            self.log_error(error_msg)
            return False, error_msg

    def move_file(self, src: Union[str, Path], dst: Union[str, Path]) -> Tuple[bool, str]:
        """
        Déplace un fichier avec une barre de progression.
        Si le déplacement direct échoue, copie puis supprime.
        
        Args:
            src: Chemin source
            dst: Chemin destination
            
        Returns:
            Tuple (success, message)
        """
        try:
            # Essayer d'abord un simple déplacement (rapide si même système de fichiers)
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.rename(src, dst)
                self.log_success(f"Fichier déplacé avec succès: {dst}")
                return True, "Déplacement réussi"
            except OSError:
                # Si échec, copier puis supprimer
                self.log_info("Déplacement direct impossible, tentative de copie puis suppression")
                success, msg = self.copy_file(src, dst)
                if success:
                    os.unlink(src)
                    self.log_success(f"Fichier déplacé avec succès: {dst}")
                    return True, "Déplacement réussi"
                return False, msg
                
        except Exception as e:
            error_msg = f"Erreur lors du déplacement de {src} vers {dst}: {e}"
            self.log_error(error_msg)
            return False, error_msg

    def move_dir(self, src: Union[str, Path], dst: Union[str, Path],
                 exclude: Optional[List[str]] = None) -> Tuple[bool, str]:
        """
        Déplace un dossier avec une barre de progression.
        Si le déplacement direct échoue, copie puis supprime.
        
        Args:
            src: Dossier source
            dst: Dossier destination
            exclude: Liste de patterns à exclure (glob)
            
        Returns:
            Tuple (success, message)
        """
        try:
            # Essayer d'abord un simple déplacement (rapide si même système de fichiers)
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.rename(src, dst)
                self.log_success(f"Dossier déplacé avec succès: {dst}")
                return True, "Déplacement réussi"
            except OSError:
                # Si échec, copier puis supprimer
                self.log_info("Déplacement direct impossible, tentative de copie puis suppression")
                success, msg = self.copy_dir(src, dst, exclude)
                if success:
                    shutil.rmtree(src)
                    self.log_success(f"Dossier déplacé avec succès: {dst}")
                    return True, "Déplacement réussi"
                return False, msg
                
        except Exception as e:
            error_msg = f"Erreur lors du déplacement du dossier {src} vers {dst}: {e}"
            self.log_error(error_msg)
            return False, error_msg
