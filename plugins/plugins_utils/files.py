#!/usr/bin/env python3
"""
Module utilitaire pour la gestion des fichiers.
Fournit une classe Files pour gérer les opérations sur les fichiers
avec une gestion appropriée des erreurs, des logs et des barres de progression.
"""

import os
import shutil
import time
from pathlib import Path
from typing import Union, Optional, List, Tuple, Dict, Any

from .plugin_utils_base import PluginUtilsBase

class Files(PluginUtilsBase):
    """
    Classe utilitaire pour la gestion des fichiers.
    Permet de gérer les opérations sur les fichiers avec une gestion appropriée des logs et des erreurs.
    """

    def __init__(self, logger=None, target_ip=None):
        """
        Initialise un gestionnaire de fichiers.

        Args:
            logger: Instance de PluginLogger à utiliser pour la journalisation (optionnel)
            target_ip: Adresse IP cible pour les logs (optionnel, pour les exécutions SSH)
        """
        # Appel du constructeur de la classe parente
        super().__init__(logger, target_ip)

    # Les méthodes set_total_steps, next_step, update_progress, log_info, log_warning, log_error, log_debug, log_success
    # sont héritées de PluginUtilsBase et n'ont pas besoin d'être redéfinies







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
                  chunk_size: int = 1024*1024, pb_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Copie un fichier avec une barre de progression.
        
        Args:
            src: Chemin source
            dst: Chemin destination
            chunk_size: Taille des chunks en octets
            pb_id: Identifiant de la barre de progression (optionnel)
            
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
            file_name = os.path.basename(src)
            
            # Utiliser un ID spécifique pour cette opération si non fourni
            if not pb_id:
                pb_id = f"copy_{file_name}_{int(time.time())}"
                
            self.set_total_steps(chunks, pb_id)
            
            # Créer une barre visuelle avec le nom du fichier
            if self.use_visual_bars and self.logger:
                self.logger.create_bar(pb_id, chunks, f"Copie de {file_name}", "", "blue")
            else:
                self.log_info(f"Copie de {file_name}")
            
            # Copier par chunks avec progression
            with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
                copied = 0
                while True:
                    chunk = fsrc.read(chunk_size)
                    if not chunk:
                        break
                    fdst.write(chunk)
                    copied += len(chunk)
                    self.next_step(None, pb_id)
            
            # Finaliser la barre de progression
            if self.use_visual_bars and self.logger:
                self.logger.update_bar(pb_id, chunks, None, f"Copie de {file_name}", "Terminé")
                
            self.log_success(f"Fichier copié avec succès: {dst}")
            return True, "Copie réussie"
            
        except Exception as e:
            error_msg = f"Erreur lors de la copie de {src} vers {dst}: {e}"
            self.log_error(error_msg)
            return False, error_msg

    def copy_dir(self, src: Union[str, Path], dst: Union[str, Path],
                 exclude: Optional[List[str]] = None, pb_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Copie un dossier avec une barre de progression.
        
        Args:
            src: Dossier source
            dst: Dossier destination
            exclude: Liste de patterns à exclure (glob)
            pb_id: Identifiant de la barre de progression (optionnel)
            
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
            total_files = len(files_to_copy)
            dir_name = os.path.basename(str(src_path))
            
            # Utiliser un ID spécifique pour cette opération si non fourni
            if not pb_id:
                pb_id = f"copydir_{dir_name}_{int(time.time())}"
                
            self.set_total_steps(total_files, pb_id)
            
            # Créer une barre visuelle avec le nom du dossier
            if self.use_visual_bars and self.logger:
                self.logger.create_bar(pb_id, total_files, f"Copie du dossier {dir_name}", "", "blue")
            else:
                self.log_info(f"Copie du dossier {dir_name}")
            
            # Copier chaque fichier
            for i, (src_file, dst_file) in enumerate(files_to_copy):
                # Créer le dossier destination si nécessaire
                os.makedirs(dst_file.parent, exist_ok=True)
                
                # Copier le fichier
                shutil.copy2(src_file, dst_file)
                self.next_step(f"Copie de {src_file.name}", pb_id, i+1)
            
            # Finaliser la barre de progression
            if self.use_visual_bars and self.logger:
                self.logger.update_bar(pb_id, total_files, None, f"Copie du dossier {dir_name}", "Terminé", "green")
                
            self.log_success(f"Dossier copié avec succès: {dst}")
            return True, "Copie réussie"
            
        except Exception as e:
            error_msg = f"Erreur lors de la copie du dossier {src} vers {dst}: {e}"
            self.log_error(error_msg)
            
            # Marquer la barre comme en erreur
            if self.use_visual_bars and self.logger and pb_id:
                self.logger.update_bar(pb_id, 0, total_files, f"Erreur: {dir_name}", "", "red")
                
            return False, error_msg

    def move_file(self, src: Union[str, Path], dst: Union[str, Path], pb_id: Optional[str] = None) -> Tuple[bool, str]:
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
                success, msg = self.copy_file(src, dst, pb_id=pb_id)
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
                 exclude: Optional[List[str]] = None, pb_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Déplace un dossier avec une barre de progression.
        Si le déplacement direct échoue, copie puis supprime.
        
        Args:
            src: Dossier source
            dst: Dossier destination
            exclude: Liste de patterns à exclure (glob)
            pb_id: Identifiant de la barre de progression (optionnel)
            
        Returns:
            Tuple (success, message)
        """
        try:
            # Créer un ID pour cette opération si non fourni
            dir_name = os.path.basename(str(src))
            if not pb_id:
                pb_id = f"movedir_{dir_name}_{int(time.time())}"
                
            # Créer une barre visuelle pour le déplacement
            if self.use_visual_bars and self.logger:
                self.logger.create_bar(pb_id, 2, f"Déplacement de {dir_name}", "", "blue")
                self.logger.next_bar(pb_id, 1, "Tentative de déplacement direct...")
                
            # Essayer d'abord un simple déplacement (rapide si même système de fichiers)
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.rename(src, dst)
                
                # Finaliser la barre de progression
                if self.use_visual_bars and self.logger:
                    self.logger.update_bar(pb_id, 2, None, f"Déplacement de {dir_name}", "Terminé", "green")
                    
                self.log_success(f"Dossier déplacé avec succès: {dst}")
                return True, "Déplacement réussi"
            except OSError:
                # Si échec, copier puis supprimer
                self.log_info("Déplacement direct impossible, tentative de copie puis suppression")
                
                # Mettre à jour la barre de progression
                if self.use_visual_bars and self.logger:
                    self.logger.update_bar(pb_id, 1, None, f"Déplacement de {dir_name}", "Copie en cours...", "yellow")
                
                # Utiliser le même ID pour la copie
                success, msg = self.copy_dir(src, dst, exclude, pb_id)
                if success:
                    shutil.rmtree(src)
                    
                    # Finaliser la barre de progression
                    if self.use_visual_bars and self.logger:
                        self.logger.update_bar(pb_id, 2, None, f"Déplacement de {dir_name}", "Terminé", "green")
                        
                    self.log_success(f"Dossier déplacé avec succès: {dst}")
                    return True, "Déplacement réussi"
                else:
                    # Marquer la barre comme en erreur
                    if self.use_visual_bars and self.logger:
                        self.logger.update_bar(pb_id, 1, 2, f"Erreur: {dir_name}", "", "red")
                        
                return False, msg
                
        except Exception as e:
            error_msg = f"Erreur lors du déplacement du dossier {src} vers {dst}: {e}"
            self.log_error(error_msg)
            
            # Marquer la barre comme en erreur
            if self.use_visual_bars and self.logger and pb_id:
                self.logger.update_bar(pb_id, 0, 2, f"Erreur: {os.path.basename(str(src))}", "", "red")
                
            return False, error_msg
