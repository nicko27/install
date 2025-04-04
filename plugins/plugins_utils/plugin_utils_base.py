#!/usr/bin/env python3
"""
Module utilitaire de base pour les plugins.
Fournit une classe de base avec des fonctionnalités communes de journalisation
et de gestion des barres de progression.
"""

import time
from typing import Union, Optional, Any, Dict

class PluginUtilsBase:
    """
    Classe de base pour les utilitaires de plugins.
    Fournit des fonctionnalités communes de journalisation et de gestion des barres de progression.
    """

    def __init__(self, logger=None, target_ip=None):
        """
        Initialise un utilitaire de base pour les plugins.

        Args:
            logger: Instance de PluginLogger à utiliser pour la journalisation (optionnel)
            target_ip: Adresse IP cible pour les logs (optionnel, pour les exécutions SSH)
        """
        self.logger = logger
        self.target_ip = target_ip

        # Variables pour la gestion de la progression
        self.total_steps = 1
        self.current_step = 0
        self.default_pb_id = "main"
        self.use_visual_bars = True  # Utiliser les barres visuelles par défaut

        # Si aucun logger n'est fourni, essayer d'en créer un temporaire
        if self.logger is None:
            try:
                from .plugin_logger import PluginLogger
                self.logger = PluginLogger()
            except Exception as e:
                # Fallback si impossible de créer un logger
                print(f"Impossible de créer un logger: {e}")
                pass

    def set_total_steps(self, total, pb_id=None):
        """
        Définit le nombre total d'étapes pour calculer les pourcentages.

        Args:
            total: Nombre total d'étapes
            pb_id: Identifiant de la barre de progression (optionnel)
        """
        self.total_steps = max(1, total)
        self.current_step = 0

        if self.logger:
            if pb_id:
                self.logger.set_total_steps(total, pb_id)
                
                # Créer une barre visuelle si activé
                if self.use_visual_bars:
                    self.logger.create_bar(pb_id, total)
            else:
                self.logger.set_total_steps(total, self.default_pb_id)
                
                # Créer une barre visuelle si activé
                if self.use_visual_bars:
                    self.logger.create_bar(self.default_pb_id, total)

    def next_step(self, message=None, pb_id=None, current_step=None):
        """
        Passe à l'étape suivante et met à jour la progression.

        Args:
            message: Message optionnel à afficher
            pb_id: Identifiant de la barre de progression (optionnel)
            current_step: Étape actuelle spécifique (optionnel)

        Returns:
            int: Étape actuelle
        """
        if current_step is not None:
            self.current_step = current_step
        else:
            self.current_step += 1
        
        current = min(self.current_step, self.total_steps)

        # Mise à jour de la progression
        if self.logger:
            # Mise à jour de la progression numérique
            bar_id = pb_id if pb_id else self.default_pb_id
            self.logger.next_step(bar_id, current_step)
            
            # Mise à jour de la barre visuelle si activée
            if self.use_visual_bars:
                pre_text = message if message else ""
                self.logger.next_bar(bar_id, current_step, pre_text)
                    
            # Afficher le message séparément si on utilise les barres visuelles
            if message and not self.use_visual_bars:
                self.logger.info(message)
        else:
            progress = int(current / self.total_steps * 100)
            print(f"[PROGRESSION] {progress}% ({current}/{self.total_steps})")
            if message:
                print(f"[INFO] {message}")

        return current

    def update_progress(self, percentage, message=None, pb_id=None):
        """
        Met à jour la progression sans passer à l'étape suivante.
        Utile pour les opérations longues avec progression continue.

        Args:
            percentage: Pourcentage de progression (0.0 à 1.0)
            message: Message optionnel à afficher
            pb_id: Identifiant de la barre de progression (optionnel)
        """
        if self.logger:
            # Calculer l'étape actuelle en fonction du pourcentage
            current_step = int(percentage * self.total_steps)
            
            # Mise à jour de la progression numérique
            self.logger.update_progress(percentage)
            
            # Mise à jour de la barre visuelle si activée
            if self.use_visual_bars:
                bar_id = pb_id if pb_id else self.default_pb_id
                pre_text = message if message else ""
                self.logger.update_bar(bar_id, current_step, None, pre_text)
            elif message:
                self.logger.info(message)
        else:
            progress = int(percentage * 100)
            print(f"[PROGRESSION] {progress}%")
            if message:
                print(f"[INFO] {message}")

    def log_info(self, msg):
        """Enregistre un message d'information."""
        if self.logger:
            self.logger.info(msg, target_ip=self.target_ip)
        else:
            print(f"[LOG] [INFO] {msg}")

    def log_warning(self, msg):
        """Enregistre un message d'avertissement."""
        if self.logger:
            self.logger.warning(msg, target_ip=self.target_ip)
        else:
            print(f"[LOG] [WARNING] {msg}")

    def log_error(self, msg):
        """Enregistre un message d'erreur."""
        if self.logger:
            self.logger.error(msg, target_ip=self.target_ip)
        else:
            print(f"[LOG] [ERROR] {msg}")

    def log_debug(self, msg):
        """Enregistre un message de débogage."""
        if self.logger:
            self.logger.debug(msg, target_ip=self.target_ip)
        else:
            print(f"[LOG] [DEBUG] {msg}")

    def log_success(self, msg):
        """Enregistre un message de succès."""
        if self.logger:
            self.logger.success(msg, target_ip=self.target_ip)
        else:
            print(f"[LOG] [SUCCESS] {msg}")
            
    def enable_visual_bars(self, enable: bool = True) -> None:
        """Active ou désactive l'utilisation des barres de progression visuelles."""
        self.use_visual_bars = enable
