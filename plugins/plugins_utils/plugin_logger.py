#!/usr/bin/env python3
"""
Module utilitaire pour les logs standardisés en format JSONL.
Supporte plusieurs barres de progression avec styles personnalisables.
"""

import os
import sys
import logging
import time
import tempfile
import json
from datetime import datetime
from typing import Dict, Any, Optional, Union

class PluginLogger:
    def __init__(self, plugin_name=None, instance_id=None, ssh_mode=False, bar_width=20):
        self.plugin_name = plugin_name
        self.instance_id = instance_id
        self.total_steps = 1
        self.current_step = 0
        self.ssh_mode = ssh_mode
        self.bar_width = bar_width  # Nouvelle propriété pour la largeur de la barre
        
        # Gestion des progressbars
        self.progressbars = {}
        self.default_pb = "main"
        self.progressbars[self.default_pb] = {
            "total_steps": 1,
            "current_step": 0
        }
        
        # Gestion des barres de progression visuelles
        self.bars = {}
        
        # Styles par défaut pour les barres
        self.default_filled_char = "■"  # Carré plein
        self.default_empty_char = "□"   # Carré vide
        
        self.init_logs()

    def init_logs(self):
        if self.plugin_name is not None and self.instance_id is not None:
            # Déterminer le répertoire des logs
            env_log_dir = os.environ.get('PCUTILS_LOG_DIR')
            
            if env_log_dir:
                log_dir = env_log_dir
            elif self.ssh_mode:
                log_dir = "/tmp/pcUtils_logs"
            else:
                log_dir = "logs"

            try:
                os.makedirs(log_dir, exist_ok=True)
                try:
                    os.chmod(log_dir, 0o777)
                except Exception as perm_error:
                    self._emit_log("warning", f"Impossible de modifier les permissions du répertoire {log_dir}: {perm_error}")
            except Exception as e:
                log_dir = os.path.join(tempfile.gettempdir(), 'pcUtils_logs')
                os.makedirs(log_dir, exist_ok=True)

            # Configuration du fichier de log
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            if self.ssh_mode:
                self.log_file = f"{log_dir}/plugin_{timestamp}.jsonl"
            else:
                self.log_file = f"{log_dir}/{self.plugin_name}.jsonl"

            if self.ssh_mode:
                self._emit_log("info", f"LOG_FILE:{self.log_file}")

    def _emit_log(self, level, message):
        """Émet un log au format JSONL"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "plugin_name": self.plugin_name,
            "instance_id": self.instance_id,
            "message": message
        }
        
        # Forcer le flush pour les messages de progression ou progress-text
        force_flush = level == "progress" or level == "progress-text"
        
        # Écrire dans le fichier
        if hasattr(self, 'log_file'):
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    json.dump(log_entry, f)
                    f.write('\n')
                    if force_flush:
                        f.flush()
                        os.fsync(f.fileno())  # Force l'écriture sur le disque
            except Exception as e:
                print(f"Erreur d'écriture dans le fichier de log: {e}", file=sys.stderr)

        # Toujours émettre sur stdout pour la compatibilité
        print(json.dumps(log_entry), flush=True)
        if force_flush:
            sys.stdout.flush()

    def update_progress(self, percentage, current_step=None, total_steps=None):
        """Met à jour la progression"""
        if current_step is None:
            current_step = self.current_step
        if total_steps is None:
            total_steps = self.total_steps

        # S'assurer que le pourcentage est entre 0 et 1
        percentage = max(0.0, min(1.0, float(percentage)))

        # Créer le message de progression
        progress_message = {
            "type": "progress",
            "data": {
                "percentage": percentage,
                "current_step": current_step,
                "total_steps": total_steps
            }
        }

        # Utiliser _emit_log pour garantir le flush immédiat
        self._emit_log("progress", progress_message)

    def info(self, message):
        self._emit_log("info", message)

    def warning(self, message):
        self._emit_log("warning", message)

    def error(self, message):
        self._emit_log("error", message)

    def success(self, message):
        self._emit_log("success", message)

    def debug(self, message):
        self._emit_log("debug", message)

    def next_step(self, pb_id=None, current_step=None):
        """Passe à l'étape suivante pour une progressbar donnée"""
        if pb_id is None:
            # Comportement existant pour la compatibilité
            self.current_step += 1
            current = min(self.current_step, self.total_steps)
            self.update_progress(current / self.total_steps, current, self.total_steps)
            return current
        else:
            # Nouvelle gestion avec ID de progressbar
            if pb_id in self.progressbars:
                if current_step is not None:
                    self.progressbars[pb_id]["current_step"] = current_step
                else:
                    self.progressbars[pb_id]["current_step"] += 1
                
                current = self.progressbars[pb_id]["current_step"]
                total = self.progressbars[pb_id]["total_steps"]
                
                # Mettre à jour la progression numérique
                self.update_progress(current / total, current, total)
                
                return current
            return 0

    def set_total_steps(self, total, pb_id=None):
        """Définit le nombre total d'étapes pour une progressbar"""
        if pb_id is None:
            # Comportement existant
            self.total_steps = max(1, total)
            self.current_step = 0
        else:
            # Nouvelle gestion avec ID
            if pb_id in self.progressbars:
                self.progressbars[pb_id]["total_steps"] = max(1, total)
                self.progressbars[pb_id]["current_step"] = 0
            else:
                # Si la barre n'existe pas, la créer
                self.new_pb(pb_id, total)

    def new_pb(self, pb_id: str, total: int = 1) -> None:
        """Crée une nouvelle progressbar avec l'ID spécifié"""
        self.progressbars[pb_id] = {
            "total_steps": max(1, total),
            "current_step": 0
        }

    # Méthodes pour les barres de progression visuelles
    
    def create_bar(self, id: str, total: int = 1, pre_text: str = "", post_text: str = "", 
                  color: str = "blue", filled_char: str = None, empty_char: str = None,
                  bar_width: Optional[int] = None) -> None:
        """
        Crée une nouvelle barre de progression visuelle
        
        Args:
            id: Identifiant unique de la barre (utilisé pour les mises à jour ultérieures)
            total: Nombre total d'étapes
            pre_text: Texte descriptif affiché avant la barre
            post_text: Texte descriptif affiché après la barre
            color: Couleur de la barre ("blue", "green", "red", "yellow", "cyan", "magenta", etc.)
            filled_char: Caractère pour les parties remplies de la barre (défaut: "■")
            empty_char: Caractère pour les parties vides de la barre (défaut: "□")
            bar_width: Largeur spécifique pour cette barre (défaut: utilise self.bar_width)
        """
        # Utiliser la largeur spécifique de cette barre ou la largeur globale
        width = bar_width if bar_width is not None else self.bar_width
        
        self.bars[id] = {
            "total_steps": max(1, total),
            "current_step": 0,
            "pre_text": pre_text,
            "post_text": post_text,
            "color": color,
            "filled_char": filled_char or self.default_filled_char,
            "empty_char": empty_char or self.default_empty_char,
            "bar_width": width
        }
        
        # Initialiser la barre à 0%
        self._emit_bar(id, 0, total, pre_text, post_text, color, 
                     filled_char or self.default_filled_char, 
                     empty_char or self.default_empty_char,
                     width)
    
    def update_bar(self, id: str, current: int, total: Optional[int] = None, 
                  pre_text: Optional[str] = None, post_text: Optional[str] = None, 
                  color: Optional[str] = None, filled_char: Optional[str] = None, 
                  empty_char: Optional[str] = None, bar_width: Optional[int] = None) -> None:
        """
        Met à jour une barre de progression visuelle existante
        
        Args:
            id: Identifiant de la barre
            current: Étape courante
            total: Nouveau total (optionnel)
            pre_text: Nouveau texte descriptif avant la barre (optionnel)
            post_text: Nouveau texte descriptif après la barre (optionnel)
            color: Nouvelle couleur (optionnel)
            filled_char: Nouveau caractère pour les parties remplies (optionnel)
            empty_char: Nouveau caractère pour les parties vides (optionnel)
            bar_width: Nouvelle largeur pour la barre (optionnel)
        """
        if id in self.bars:
            # Mettre à jour les valeurs
            self.bars[id]["current_step"] = current
            
            if total is not None:
                self.bars[id]["total_steps"] = max(1, total)
                
            if pre_text is not None:
                self.bars[id]["pre_text"] = pre_text
                
            if post_text is not None:
                self.bars[id]["post_text"] = post_text
                
            if color is not None:
                self.bars[id]["color"] = color
                
            if filled_char is not None:
                self.bars[id]["filled_char"] = filled_char
                
            if empty_char is not None:
                self.bars[id]["empty_char"] = empty_char
                
            if bar_width is not None:
                self.bars[id]["bar_width"] = bar_width
            
            # Émettre la barre mise à jour
            self._emit_bar(
                id,
                current,
                self.bars[id]["total_steps"],
                self.bars[id]["pre_text"],
                self.bars[id]["post_text"],
                self.bars[id]["color"],
                self.bars[id]["filled_char"],
                self.bars[id]["empty_char"],
                self.bars[id]["bar_width"]
            )
    
    def next_bar(self, id: str, current_step: Optional[int] = None, 
                pre_text: Optional[str] = None, post_text: Optional[str] = None) -> int:
        """
        Avance la barre de progression spécifiée d'une étape ou la définit à une étape spécifique
        
        Args:
            id: Identifiant de la barre de progression
            current_step: Étape courante (si None, incrémente l'étape actuelle)
            pre_text: Nouveau texte à afficher avant la barre (optionnel)
            post_text: Nouveau texte à afficher après la barre (optionnel)
            
        Returns:
            int: Numéro de l'étape courante après mise à jour
        """
        if id in self.bars:
            if current_step is not None:
                self.bars[id]["current_step"] = current_step
            else:
                self.bars[id]["current_step"] += 1
            
            # Mettre à jour les textes si fournis
            if pre_text is not None:
                self.bars[id]["pre_text"] = pre_text
            
            if post_text is not None:
                self.bars[id]["post_text"] = post_text
            
            current = self.bars[id]["current_step"]
            total = self.bars[id]["total_steps"]
            
            # Émettre la barre mise à jour
            self._emit_bar(
                id, 
                current, 
                total,
                self.bars[id]["pre_text"],
                self.bars[id]["post_text"],
                self.bars[id]["color"],
                self.bars[id]["filled_char"],
                self.bars[id]["empty_char"],
                self.bars[id]["bar_width"]
            )
            
            return current
        return 0
    
    def delete_bar(self, id: str) -> None:
        """
        Supprime une barre de progression visuelle
        
        Args:
            id: Identifiant de la barre à supprimer
        """
        if id in self.bars:
            # Créer un message pour stopper la barre
            progress_message = {
                "type": "progress-text",
                "data": {
                    "id": id,
                    "percentage": 0,
                    "current_step": 0,
                    "total_steps": 0,
                    "status": "stop",
                    "pre_text": self.bars[id].get("pre_text", ""),
                    "post_text": self.bars[id].get("post_text", ""),
                    "color": self.bars[id].get("color", "blue"),
                    "filled_char": self.bars[id].get("filled_char", self.default_filled_char),
                    "empty_char": self.bars[id].get("empty_char", self.default_empty_char),
                    "bar": ""
                }
            }

            # Utiliser _emit_log pour garantir le flush immédiat
            self._emit_log("progress-text", progress_message)
            
            # Supprimer la barre du dictionnaire
            del self.bars[id]
    
    def set_default_bar_style(self, filled_char: str, empty_char: str) -> None:
        """
        Définit le style par défaut pour toutes les nouvelles barres
        
        Args:
            filled_char: Caractère pour les parties remplies de la barre
            empty_char: Caractère pour les parties vides de la barre
        """
        self.default_filled_char = filled_char
        self.default_empty_char = empty_char
    
    def set_default_bar_width(self, width: int) -> None:
        """
        Définit la largeur par défaut pour toutes les nouvelles barres
        
        Args:
            width: Largeur de la barre en caractères
        """
        self.bar_width = max(1, width)
    
    def _emit_bar(self, id: str, current: int, total: int, 
                pre_text: str = "", post_text: str = "", color: str = "blue",
                filled_char: str = None, empty_char: str = None,
                bar_width: Optional[int] = None) -> None:
        """
        Émet une barre de progression visuelle dans les logs
        
        Args:
            id: Identifiant de la barre
            current: Étape courante
            total: Nombre total d'étapes
            pre_text: Texte descriptif avant la barre
            post_text: Texte descriptif après la barre
            color: Couleur de la barre
            filled_char: Caractère pour les parties remplies
            empty_char: Caractère pour les parties vides
            bar_width: Largeur de la barre en caractères
        """
        if filled_char is None:
            filled_char = self.default_filled_char
        if empty_char is None:
            empty_char = self.default_empty_char
        if bar_width is None:
            bar_width = self.bar_width
            
        # Calculer le pourcentage
        percentage = min(100, max(0, int((current / total) * 100)))
        
        # Configurer la largeur de la barre
        filled_width = int(bar_width * percentage / 100)
        
        # Créer la barre visuelle
        bar = filled_char * filled_width + empty_char * (bar_width - filled_width)
        
        # Créer le message complet
        progress_message = {
            "type": "progress-text",
            "data": {
                "id": id,
                "percentage": percentage,
                "current_step": current,
                "total_steps": total,
                "status": "running",
                "pre_text": pre_text,
                "post_text": post_text,
                "color": color,
                "filled_char": filled_char,
                "empty_char": empty_char,
                "bar": bar
            }
        }
        
        # Émettre un log pour afficher la barre
        self._emit_log("progress-text", progress_message)
    
    # Méthodes pour la compatibilité avec l'ancienne API
    
    def show_text_pb(self, total: int = 1, pre_text: str = "", post_text: str = "", color: str = "blue") -> None:
        """
        Méthode de compatibilité pour l'ancienne API
        Active une barre de progression avec l'ID 'default'
        """
        self.create_bar("default", total, pre_text, post_text, color)
    
    def delete_text_pb(self) -> None:
        """
        Méthode de compatibilité pour l'ancienne API
        Supprime la barre de progression 'default'
        """
        self.delete_bar("default")
    
    def next_text_step(self, current_step: Optional[int] = None, pre_text: Optional[str] = None, post_text: Optional[str] = None) -> int:
        """
        Méthode de compatibilité pour l'ancienne API
        Avance la barre 'default' d'une étape
        """
        return self.next_bar("default", current_step, pre_text, post_text)