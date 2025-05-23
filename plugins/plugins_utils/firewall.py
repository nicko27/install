# install/plugins/plugins_utils/firewall.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module utilitaire pour gérer le pare-feu système via UFW (Uncomplicated Firewall).
Utilise la commande 'ufw'.
NOTE: Nécessite que UFW soit installé et configuré sur le système cible.
"""

from plugins_utils.plugins_utils_base import PluginsUtilsBase
import os
import re
from typing import Union, Optional, List, Dict, Any, Tuple

class FirewallCommands(PluginsUtilsBase):
    """
    Classe pour gérer le pare-feu UFW.
    Hérite de PluginUtilsBase pour l'exécution de commandes.
    """

    def __init__(self, logger=None, target_ip=None):
        """Initialise le gestionnaire de pare-feu."""
        super().__init__(logger, target_ip)
        self._ufw_cmd_path: Optional[str] = None
        self._check_commands()

    def _check_commands(self):
        """Vérifie si la commande ufw est disponible et stocke son chemin."""
        cmd = 'ufw'
        success, path, _ = self.run(['which', cmd], check=False, no_output=True, error_as_warning=True)
        if success and path.strip():
            self._ufw_cmd_path = path.strip()
            self.log_debug(f"Commande '{cmd}' trouvée: {self._ufw_cmd_path}", log_levels=log_levels)
        else:
            self.log_error(f"Commande '{cmd}' non trouvée. Ce module ne fonctionnera pas. "
                           f"Installer le paquet 'ufw'.", log_levels=log_levels)

    def _run_ufw(self, args: List[str], check: bool = False, needs_sudo: bool = True, **kwargs) -> Tuple[bool, str, str]:
        """Exécute une commande ufw."""
        if not self._ufw_cmd_path:
            return False, "", "Commande 'ufw' non trouvée."
        cmd = [self._ufw_cmd_path] + args
        # Passer les kwargs (comme input_data, timeout) à la méthode run de base
        # Forcer needs_sudo=True car la plupart des commandes ufw le nécessitent
        return self.run(cmd, check=check, needs_sudo=needs_sudo, **kwargs)

    def is_active(self, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """Vérifie si UFW est actif."""
        self.log_debug("Vérification du statut UFW (ufw status)", log_levels=log_levels)
        # check=False car la commande peut échouer si ufw n'est pas installé
        success, stdout, stderr = self._run_ufw(['status'], check=False, no_output=True, error_as_warning=True)
        # La sortie contient "Status: active" ou "Statut : actif"
        is_act = success and ('status: active' in stdout.lower() or 'statut : actif' in stdout.lower())
        self.log_info(f"UFW est actif: {is_act}", log_levels=log_levels)
        return is_act

    def enable(self, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """Active le pare-feu UFW. Nécessite root."""
        self.log_info("Activation du pare-feu UFW (ufw enable)", log_levels=log_levels)
        # ufw enable demande une confirmation, il faut répondre 'y'
        # Utiliser 'yes' pour répondre automatiquement via un pipe shell
        cmd_str = f"yes | {shlex.quote(self._ufw_cmd_path)} enable"
        success, stdout, stderr = self.run(cmd_str, shell=True, check=False, needs_sudo=True)

        # Vérifier la sortie en plus du code de retour
        output = stdout + stderr
        if success or "firewall is active and enabled on system startup" in output.lower() or "le pare-feu est actif" in output.lower():
            self.log_success("UFW activé avec succès.", log_levels=log_levels)
            if stdout: self.log_info(f"Sortie ufw enable:\n{stdout}", log_levels=log_levels)
            return True
        else:
            self.log_error(f"Échec de l'activation d'UFW. Stderr: {stderr}", log_levels=log_levels)
            if stdout: self.log_info(f"Sortie ufw enable (échec):\n{stdout}", log_levels=log_levels)
            return False

    def disable(self, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """Désactive le pare-feu UFW. Nécessite root."""
        self.log_info("Désactivation du pare-feu UFW (ufw disable)", log_levels=log_levels)
        success, stdout, stderr = self._run_ufw(['disable'], check=False)
        output = stdout + stderr
        if success or "firewall stopped and disabled" in output.lower() or "pare-feu arrêté et désactivé" in output.lower():
            self.log_success("UFW désactivé avec succès.", log_levels=log_levels)
            if stdout: self.log_info(f"Sortie ufw disable:\n{stdout}", log_levels=log_levels)
            return True
        else:
            # Gérer le cas où il est déjà inactif
            if "is inactive" in stderr.lower() or "est inactif" in stderr.lower():
                 self.log_info("UFW était déjà inactif.", log_levels=log_levels)
                 return True
            self.log_error(f"Échec de la désactivation d'UFW. Stderr: {stderr}", log_levels=log_levels)
            if stdout: self.log_info(f"Sortie ufw disable (échec):\n{stdout}", log_levels=log_levels)
            return False

    def reset(self, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """Réinitialise UFW à ses paramètres par défaut. Opération dangereuse. Nécessite root."""
        self.log_warning("Réinitialisation d'UFW à ses paramètres par défaut ! OPÉRATION DANGEREUSE !", log_levels=log_levels)
        # ufw reset demande confirmation
        cmd_str = f"yes | {shlex.quote(self._ufw_cmd_path)} reset"
        success, stdout, stderr = self.run(cmd_str, shell=True, check=False, needs_sudo=True)
        if success:
            self.log_success("UFW réinitialisé avec succès.", log_levels=log_levels)
            if stdout: self.log_info(f"Sortie ufw reset:\n{stdout}", log_levels=log_levels)
            return True
        else:
            self.log_error(f"Échec de la réinitialisation d'UFW. Stderr: {stderr}", log_levels=log_levels)
            if stdout: self.log_info(f"Sortie ufw reset (échec):\n{stdout}", log_levels=log_levels)
            return False

    def get_status(self, numbered: bool = True, log_levels: Optional[Dict[str, str]] = None) -> Optional[str]:
        """
        Récupère le statut et les règles UFW.

        Args:
            numbered: Si True, affiche les règles numérotées (utile pour la suppression).

        Returns:
            La sortie texte de 'ufw status' ou None si erreur.
        """
        self.log_info(f"Récupération du statut UFW ({'numéroté' if numbered else 'standard'})", log_levels=log_levels)
        args = ['status']
        if numbered:
            args.append('numbered')
        else:
             args.append('verbose') # verbose donne plus de détails

        # Le statut peut nécessiter sudo pour voir toutes les règles/infos
        success, stdout, stderr = self._run_ufw(args, check=False, needs_sudo=True)
        if not success:
             # Gérer le cas où UFW est inactif
             if "inactive" in stdout.lower() or "inactif" in stdout.lower():
                  self.log_info("Statut UFW: Inactif", log_levels=log_levels)
                  return stdout # Retourner la sortie même si inactif
             self.log_error(f"Échec de la récupération du statut UFW. Stderr: {stderr}", log_levels=log_levels)
             return None

        self.log_debug(f"Statut UFW récupéré:\n{stdout}", log_levels=log_levels)
        return stdout

    def _manage_rule(self, action: str, rule: str) -> bool:
        """Fonction helper pour ajouter/supprimer des règles (allow, deny, reject, limit, delete)."""
        action_map = {
            'allow': 'Autorisation',
            'deny': 'Refus',
            'reject': 'Rejet',
            'limit': 'Limitation',
            'delete': 'Suppression'
        }
        action_fr = action_map.get(action, action.capitalize())
        self.log_info(f"{action_fr} de la règle UFW: {rule}", log_levels=log_levels)

        # 'delete' demande confirmation, les autres non par défaut
        cmd: Union[List[str], str]
        use_shell = False
        if action == 'delete':
             # Utiliser 'yes' pour confirmer la suppression
             cmd_str = f"yes | {shlex.quote(self._ufw_cmd_path)} delete {shlex.quote(rule)}"
             cmd = cmd_str
             use_shell = True
        else:
             # Découper la règle en arguments pour ufw
             # Attention: une règle complexe avec 'from x to y proto z' doit être passée correctement
             # shlex.split peut aider si la règle est bien formée
             try:
                  rule_args = shlex.split(rule)
                  cmd = [action] + rule_args
             except ValueError:
                  self.log_warning(f"Impossible de découper la règle '{rule}' correctement, passage en argument unique.", log_levels=log_levels)
                  cmd = [action, rule] # Fallback

        success, stdout, stderr = self._run_ufw(cmd, shell=use_shell, check=False) # Utilise _run_ufw qui ajoute le chemin ufw
        output = stdout + stderr

        if success:
            # Vérifier la sortie pour confirmation
            if f"rule {action.replace('e', '')}ed" in output.lower() or \
               f"règle ajoutée" in output.lower() or \
               f"règle mise à jour" in output.lower() or \
               f"règle supprimée" in output.lower():
                 self.log_success(f"Règle '{rule}' ({action}) appliquée avec succès.", log_levels=log_levels)
                 if stdout: self.log_info(f"Sortie ufw {action}:\n{stdout}", log_levels=log_levels)
                 return True
            # Cas où la règle existe/n'existe pas déjà
            elif "skipping adding existing rule" in output.lower() or \
                 "règle existe déjà" in output.lower() or \
                 ("delete" in action and ("could not find rule" in output.lower() or "impossible de trouver" in output.lower())):
                 self.log_warning(f"La règle '{rule}' ({action}) existe/n'existe pas déjà.", log_levels=log_levels)
                 return True # Succès car état désiré atteint
            else:
                 # Succès mais sortie inconnue? Log et considérer comme succès
                 self.log_warning(f"La commande ufw {action} a réussi mais la sortie est inattendue:\n{output}", log_levels=log_levels)
                 return True
        else:
            self.log_error(f"Échec de l'opération '{action}' pour la règle '{rule}'. Stderr: {stderr}", log_levels=log_levels)
            if stdout: self.log_info(f"Sortie ufw {action} (échec):\n{stdout}", log_levels=log_levels)
            return False

    def allow(self, rule: str, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """Ajoute une règle 'allow'. Nécessite root."""
        return self._manage_rule('allow', rule)

    def deny(self, rule: str, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """Ajoute une règle 'deny'. Nécessite root."""
        return self._manage_rule('deny', rule)

    def reject(self, rule: str, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """Ajoute une règle 'reject'. Nécessite root."""
        return self._manage_rule('reject', rule)

    def limit(self, rule: str, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """Ajoute une règle 'limit' (limite les connexions depuis une IP). Nécessite root."""
        return self._manage_rule('limit', rule)

    def delete_rule(self, rule_or_number: Union[str, int], log_levels: Optional[Dict[str, str]] = None) -> bool:
        """Supprime une règle UFW par son numéro ou sa spécification. Nécessite root."""
        return self._manage_rule('delete', str(rule_or_number))

    def set_default_policy(self, policy: str, direction: str = 'incoming', log_levels: Optional[Dict[str, str]] = None) -> bool:
        """
        Définit la politique par défaut pour un trafic donné. Nécessite root.

        Args:
            policy: Politique à appliquer ('allow', 'deny', 'reject').
            direction: Direction du trafic ('incoming', 'outgoing', 'routed').

        Returns:
            bool: True si succès.
        """
        valid_policies = ['allow', 'deny', 'reject']
        valid_directions = ['incoming', 'outgoing', 'routed']
        policy_lower = policy.lower()
        direction_lower = direction.lower()

        if policy_lower not in valid_policies:
            self.log_error(f"Politique invalide: {policy}. Choisir parmi {valid_policies}.", log_levels=log_levels)
            return False
        if direction_lower not in valid_directions:
            self.log_error(f"Direction invalide: {direction}. Choisir parmi {valid_directions}.", log_levels=log_levels)
            return False

        self.log_info(f"Définition de la politique par défaut '{policy_lower}' pour le trafic '{direction_lower}'", log_levels=log_levels)
        cmd = ['default', policy_lower, direction_lower]
        success, stdout, stderr = self._run_ufw(cmd, check=False)

        if success:
            self.log_success(f"Politique par défaut '{direction_lower}' définie à '{policy_lower}'.", log_levels=log_levels)
            if stdout: self.log_info(f"Sortie ufw default:\n{stdout}", log_levels=log_levels)
            return True
        else:
            self.log_error(f"Échec de la définition de la politique par défaut. Stderr: {stderr}", log_levels=log_levels)
            return False

    def reload(self, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """Recharge la configuration UFW sans interrompre les connexions existantes. Nécessite root."""
        self.log_info("Rechargement de la configuration UFW (ufw reload)", log_levels=log_levels)
        success, stdout, stderr = self._run_ufw(['reload'], check=False)
        output = stdout + stderr
        if success or "firewall reloaded" in output.lower() or "pare-feu rechargé" in output.lower():
            self.log_success("Configuration UFW rechargée avec succès.", log_levels=log_levels)
            if stdout: self.log_info(f"Sortie ufw reload:\n{stdout}", log_levels=log_levels)
            return True
        else:
            # Vérifier si l'erreur est due à UFW inactif
            if "skipping reload" in output.lower():
                 self.log_warning("Rechargement ignoré car UFW est inactif.", log_levels=log_levels)
                 return False # Rechargement n'a pas eu lieu
            self.log_error(f"Échec du rechargement d'UFW. Stderr: {stderr}", log_levels=log_levels)
            return False