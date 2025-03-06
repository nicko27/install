"""
Classe utilitaire pour la gestion des logs dans les plugins.
Fournit une interface simple pour générer des messages au format standardisé.
"""

import sys
import logging
from datetime import datetime
from typing import Optional

class PluginLogger:
    """
    Classe utilitaire pour les plugins permettant d'envoyer des messages standardisés
    et des mises à jour de progression à l'application principale.
    """
    
    def __init__(self, plugin_name: str = None):
        """
        Initialise le logger avec un nom de plugin optionnel.
        
        Args:
            plugin_name (str, optional): Nom du plugin pour préfixer les messages
        """
        self.plugin_name = plugin_name
        
        # Configuration du logger pour les fichiers si nécessaire
        self.logger = logging.getLogger(plugin_name or "plugin")
        
        # Nombre d'étapes total pour le calcul de progression
        self.total_steps = 1
        self.current_step = 0
    
    def set_total_steps(self, total: int) -> None:
        """
        Définit le nombre total d'étapes pour le calcul des pourcentages.
        
        Args:
            total (int): Nombre total d'étapes
        """
        self.total_steps = max(1, total)  # Minimum 1 pour éviter division par zéro
        self.current_step = 0
    
    def next_step(self) -> int:
        """
        Passe à l'étape suivante et envoie une mise à jour de progression.
        
        Returns:
            int: Numéro de l'étape actuelle
        """
        self.current_step += 1
        current = min(self.current_step, self.total_steps)  # Ne pas dépasser le total
        self.update_progress(current / self.total_steps, current, self.total_steps)
        return current
    
    def info(self, message: str) -> None:
        """
        Envoie un message d'information.
        
        Args:
            message (str): Message à envoyer
        """
        print(f"[LOG] [INFO] {message}", flush=True)
        self.logger.info(message)
    
    def warning(self, message: str) -> None:
        """
        Envoie un message d'avertissement.
        
        Args:
            message (str): Message à envoyer
        """
        print(f"[LOG] [WARNING] {message}", flush=True)
        self.logger.warning(message)
    
    def error(self, message: str) -> None:
        """
        Envoie un message d'erreur.
        
        Args:
            message (str): Message à envoyer
        """
        print(f"[LOG] [ERROR] {message}", flush=True)
        self.logger.error(message)
    
    def success(self, message: str) -> None:
        """
        Envoie un message de succès.
        
        Args:
            message (str): Message à envoyer
        """
        print(f"[LOG] [SUCCESS] {message}", flush=True)
        self.logger.info(message)
    
    def debug(self, message: str) -> None:
        """
        Envoie un message de débogage.
        
        Args:
            message (str): Message à envoyer
        """
        print(f"[LOG] [DEBUG] {message}", flush=True)
        self.logger.debug(message)
    
    def update_progress(self, percentage: float, current_step: Optional[int] = None, total_steps: Optional[int] = None) -> None:
        """
        Envoie une mise à jour de progression.
        
        Args:
            percentage (float): Pourcentage de progression (0.0 à 1.0)
            current_step (int, optional): Étape actuelle
            total_steps (int, optional): Nombre total d'étapes
        """
        # Calculer le pourcentage si non fourni mais étapes fournies
        if current_step is not None and total_steps is not None:
            percentage = current_step / total_steps
        
        # Convertir en pourcentage (0-100)
        percent = int(max(0, min(100, percentage * 100)))
        
        # Si étapes non fournies, utiliser les valeurs de l'instance
        if current_step is None:
            current_step = self.current_step
        if total_steps is None:
            total_steps = self.total_steps
        
        # Envoyer la mise à jour au format standardisé
        print(f"[PROGRESS] {percent} {current_step} {total_steps}", flush=True)