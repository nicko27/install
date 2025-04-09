# install/plugins/plugins_utils/lvm.py
#!/usr/bin/env python3
"""
Module utilitaire pour la gestion de LVM (Logical Volume Manager) sous Linux.
Utilise les commandes pvs, vgs, lvs, pvcreate, vgcreate, lvcreate, etc.
Privilégie la sortie JSON lorsque disponible (--reportformat json).
"""

from plugins_utils.plugins_utils_base import PluginsUtilsBase
import json
from typing import Union, Optional, List, Dict, Any, Tuple

# Unités de taille LVM courantes
LVM_UNITS = {'k', 'm', 'g', 't', 'p', 'e'} # Kilo, Mega, Giga, Tera, Peta, Exa (puissances de 1024)

class LvmCommands(PluginsUtilsBase):
    """
    Classe pour gérer LVM (Physical Volumes, Volume Groups, Logical Volumes).
    Hérite de PluginUtilsBase pour l'exécution de commandes.
    """

    def __init__(self, logger=None, target_ip=None):
        """Initialise le gestionnaire LVM."""
        super().__init__(logger, target_ip)
        self._check_commands()

    def _check_commands(self):
        """Vérifie si les commandes LVM de base sont disponibles."""
        cmds = ['pvs', 'vgs', 'lvs', 'pvcreate', 'vgcreate', 'lvcreate', 'vgextend', 'lvextend', 'lvremove', 'vgremove', 'pvremove', 'resize2fs', 'xfs_growfs']
        missing = []
        for cmd in cmds:
            success, _, _ = self.run(['which', cmd], check=False, no_output=True, error_as_warning=True)
            if not success:
                missing.append(cmd)
        if missing:
            self.log_warning(f"Commandes LVM/FS potentiellement manquantes: {', '.join(missing)}. "
                             f"Installer 'lvm2', 'e2fsprogs', 'xfsprogs' ou équivalent.")

    def _run_lvm_report_json(self, command: List[str]) -> Optional[List[Dict[str, Any]]]:
        """Exécute une commande LVM avec sortie JSON et la parse."""
        cmd = command + ['--reportformat', 'json']
        # LVM list commands usually don't require root, but report commands might
        success, stdout, stderr = self.run(cmd, check=False, no_output=True, needs_sudo=True) # Use sudo just in case

        if not success:
            # Vérifier si l'erreur est "not found" (peut être normal si aucun PV/VG/LV)
            if "not found" in stderr.lower():
                 self.log_info(f"Aucun objet LVM trouvé par '{' '.join(command)}'.")
                 return [] # Retourner liste vide
            self.log_error(f"Échec de la commande LVM '{' '.join(command)}'. Stderr: {stderr}")
            return None # Erreur réelle

        try:
            data = json.loads(stdout)
            # La sortie JSON est typiquement sous la clé 'report'[0]['pv'/'vg'/'lv']
            report_key = command[0][:-1] # 'pvs' -> 'pv', 'vgs' -> 'vg', 'lvs' -> 'lv'
            report = data.get('report', [])
            if report and isinstance(report, list) and report_key in report[0]:
                items = report[0][report_key]
                # Convertir les tailles numériques (ex: '10.00g') en octets si possible
                for item in items:
                    for key, value in item.items():
                        if isinstance(value, str) and value[-1].lower() in LVM_UNITS and value[:-1].replace('.', '', 1).isdigit():
                            try:
                                item[key + '_bytes'] = self._lvm_size_to_bytes(value)
                            except ValueError:
                                 pass # Garder la chaîne originale si conversion échoue
                return items
            else:
                 self.log_warning(f"Format JSON inattendu pour '{' '.join(command)}'.")
                 return [] # Retourner liste vide si format inconnu mais commande réussie
        except json.JSONDecodeError as e:
            self.log_error(f"Erreur de parsing JSON pour '{' '.join(command)}': {e}")
            self.log_debug(f"Sortie LVM brute:\n{stdout}")
            return None
        except Exception as e:
            self.log_error(f"Erreur inattendue lors du traitement LVM JSON: {e}", exc_info=True)
            return None

    def _lvm_size_to_bytes(self, size_str: str) -> int:
        """Convertit une taille LVM (ex: '10.00g') en octets."""
        size_str = size_str.lower().strip()
        unit = size_str[-1]
        if unit not in LVM_UNITS:
            raise ValueError(f"Unité de taille LVM inconnue: {unit}")

        value = float(size_str[:-1])
        multipliers = {'k': 1024, 'm': 1024**2, 'g': 1024**3, 't': 1024**4, 'p': 1024**5, 'e': 1024**6}
        return int(value * multipliers[unit])

    def _format_lvm_size(self, size: Union[str, int], units: str = 'G') -> str:
        """Formate une taille pour les commandes LVM (ex: '10G', '512M')."""
        size_str = str(size).upper()
        # Si l'unité est déjà présente, la retourner telle quelle
        if size_str[-1] in 'KMGTP':
             return size_str
        # Ajouter l'unité par défaut
        return f"{size_str}{units.upper()}"

    # --- Commandes de Listage ---

    def list_pvs(self, vg_name: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Liste les Physical Volumes (PVs)."""
        self.log_info(f"Listage des PVs {'dans VG ' + vg_name if vg_name else ''}")
        cmd = ['pvs']
        if vg_name: cmd.append(vg_name)
        return self._run_lvm_report_json(cmd)

    def list_vgs(self) -> Optional[List[Dict[str, Any]]]:
        """Liste les Volume Groups (VGs)."""
        self.log_info("Listage des VGs")
        return self._run_lvm_report_json(['vgs'])

    def list_lvs(self, vg_name: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """Liste les Logical Volumes (LVs)."""
        self.log_info(f"Listage des LVs {'dans VG ' + vg_name if vg_name else ''}")
        cmd = ['lvs']
        if vg_name: cmd.append(vg_name)
        return self._run_lvm_report_json(cmd)

    # --- Commandes de Création ---

    def create_pv(self, device: str) -> bool:
        """Initialise un disque ou une partition comme Physical Volume (PV)."""
        self.log_info(f"Initialisation du PV sur: {device}")
        # Utiliser -f pour forcer si nécessaire? Pour l'instant non.
        # Utiliser -y pour confirmer sans prompt
        cmd = ['pvcreate', '-y', device]
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)
        if success:
            self.log_success(f"PV créé avec succès sur {device}.")
            if stdout: self.log_info(f"Sortie pvcreate:\n{stdout}")
            return True
        else:
            self.log_error(f"Échec de la création du PV sur {device}. Stderr: {stderr}")
            return False

    def create_vg(self, vg_name: str, devices: List[str]) -> bool:
        """Crée un Volume Group (VG) à partir d'un ou plusieurs PVs."""
        if not devices:
            self.log_error("Au moins un périphérique PV est requis pour créer un VG.")
            return False
        self.log_info(f"Création du VG '{vg_name}' avec les PVs: {', '.join(devices)}")
        cmd = ['vgcreate', vg_name] + devices
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)
        if success:
            self.log_success(f"VG '{vg_name}' créé avec succès.")
            if stdout: self.log_info(f"Sortie vgcreate:\n{stdout}")
            return True
        else:
            self.log_error(f"Échec de la création du VG '{vg_name}'. Stderr: {stderr}")
            return False

    def create_lv_linear(self, vg_name: str, lv_name: str, size: Union[str, int], units: str = 'G') -> bool:
        """
        Crée un Logical Volume (LV) linéaire avec une taille fixe.

        Args:
            vg_name: Nom du Volume Group parent.
            lv_name: Nom du nouveau Logical Volume.
            size: Taille du volume (nombre).
            units: Unité de taille (k, m, g, t, p, e - défaut G).

        Returns:
            bool: True si succès.
        """
        size_str = self._format_lvm_size(size, units)
        self.log_info(f"Création du LV linéaire '{lv_name}' dans VG '{vg_name}' (taille: {size_str})")
        cmd = ['lvcreate', '-L', size_str, '-n', lv_name, vg_name]
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)
        if success:
            self.log_success(f"LV '{lv_name}' créé avec succès.")
            if stdout: self.log_info(f"Sortie lvcreate:\n{stdout}")
            return True
        else:
            self.log_error(f"Échec de la création du LV '{lv_name}'. Stderr: {stderr}")
            return False

    def create_lv_percent(self, vg_name: str, lv_name: str, percent: int, pool: str = 'VG') -> bool:
        """
        Crée un Logical Volume (LV) en utilisant un pourcentage de l'espace disponible.

        Args:
            vg_name: Nom du Volume Group parent.
            lv_name: Nom du nouveau Logical Volume.
            percent: Pourcentage de l'espace à utiliser (1-100).
            pool: Pool d'espace à utiliser ('VG', 'FREE' - défaut VG).

        Returns:
            bool: True si succès.
        """
        if not 1 <= percent <= 100:
            self.log_error("Le pourcentage doit être entre 1 et 100.")
            return False
        pool_upper = pool.upper()
        if pool_upper not in ['VG', 'FREE']:
            self.log_error("Le pool doit être 'VG' ou 'FREE'.")
            return False

        self.log_info(f"Création du LV '{lv_name}' dans VG '{vg_name}' ({percent}% de {pool_upper})")
        cmd = ['lvcreate', '-l', f"{percent}%{pool_upper}", '-n', lv_name, vg_name]
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)
        if success:
            self.log_success(f"LV '{lv_name}' créé avec succès.")
            if stdout: self.log_info(f"Sortie lvcreate:\n{stdout}")
            return True
        else:
            self.log_error(f"Échec de la création du LV '{lv_name}'. Stderr: {stderr}")
            return False

    # --- Commandes de Modification ---

    def extend_vg(self, vg_name: str, devices: List[str]) -> bool:
        """Ajoute un ou plusieurs PVs à un Volume Group existant."""
        if not devices:
            self.log_error("Aucun périphérique PV spécifié pour étendre le VG.")
            return False
        self.log_info(f"Extension du VG '{vg_name}' avec les PVs: {', '.join(devices)}")
        cmd = ['vgextend', vg_name] + devices
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)
        if success:
            self.log_success(f"VG '{vg_name}' étendu avec succès.")
            if stdout: self.log_info(f"Sortie vgextend:\n{stdout}")
            return True
        else:
            self.log_error(f"Échec de l'extension du VG '{vg_name}'. Stderr: {stderr}")
            return False

    def extend_lv(self, lv_path_or_name: str, size_increase: Union[str, int], units: str = 'G', resize_fs: bool = True) -> bool:
        """
        Étend un Logical Volume et optionnellement son système de fichiers.

        Args:
            lv_path_or_name: Chemin complet (/dev/vg/lv) ou nom relatif (vg/lv) du LV.
            size_increase: Taille à ajouter (nombre).
            units: Unité de taille pour l'ajout (k, m, g, t - défaut G).
            resize_fs: Si True, tente de redimensionner le système de fichiers après l'extension.

        Returns:
            bool: True si l'extension (et potentiellement le redimensionnement FS) a réussi.
        """
        size_str = self._format_lvm_size(size_increase, units)
        # Utiliser le chemin complet est plus sûr
        full_lv_path = self._resolve_lv_path(lv_path_or_name)
        if not full_lv_path:
             self.log_error(f"Impossible de résoudre le chemin pour LV '{lv_path_or_name}'.")
             return False

        self.log_info(f"Extension du LV '{full_lv_path}' de +{size_str}")
        # Utiliser -L +... pour ajouter de l'espace
        cmd_extend = ['lvextend', '-L', f"+{size_str}", full_lv_path]
        success, stdout, stderr = self.run(cmd_extend, check=False, needs_sudo=True)

        if not success:
            self.log_error(f"Échec de l'extension du LV '{full_lv_path}'. Stderr: {stderr}")
            return False

        self.log_success(f"LV '{full_lv_path}' étendu avec succès.")
        if stdout: self.log_info(f"Sortie lvextend:\n{stdout}")

        # Redimensionner le système de fichiers si demandé
        if resize_fs:
            return self.resize_filesystem(full_lv_path)
        else:
            return True

    def resize_filesystem(self, lv_path: str) -> bool:
        """
        Redimensionne le système de fichiers sur un LV pour utiliser tout l'espace disponible.
        Supporte ext2/3/4 et XFS.

        Args:
            lv_path: Chemin complet du Logical Volume (ex: /dev/vg_name/lv_name).

        Returns:
            bool: True si le redimensionnement a réussi.
        """
        self.log_info(f"Tentative de redimensionnement du système de fichiers sur {lv_path}")

        # 1. Détecter le type de système de fichiers
        fs_info = StorageCommands(self.logger, self.target_ip).get_filesystem_info(lv_path) # Utiliser StorageCommands
        fs_type = fs_info.get('TYPE') if fs_info else None

        if not fs_type:
            self.log_error(f"Impossible de détecter le type de système de fichiers sur {lv_path}.")
            return False

        self.log_info(f"Système de fichiers détecté: {fs_type}")

        # 2. Choisir la commande appropriée
        resize_cmd: Optional[List[str]] = None
        if fs_type.startswith('ext'): # ext2, ext3, ext4
            resize_cmd = ['resize2fs', lv_path]
        elif fs_type == 'xfs':
            # xfs_growfs nécessite le point de montage, pas le périphérique
            mount_info = StorageCommands(self.logger, self.target_ip).get_mount_info(lv_path)
            if mount_info and mount_info[0].get('TARGET'):
                mount_point = mount_info[0]['TARGET']
                resize_cmd = ['xfs_growfs', mount_point]
            else:
                self.log_error(f"Impossible de trouver le point de montage pour {lv_path} (requis pour xfs_growfs).")
                return False
        # Ajouter d'autres types de FS si nécessaire (btrfs, etc.)
        # elif fs_type == 'btrfs': resize_cmd = ['btrfs', 'filesystem', 'resize', 'max', mount_point]

        if not resize_cmd:
            self.log_warning(f"Le redimensionnement automatique pour le type de système de fichiers '{fs_type}' n'est pas supporté.")
            return False # Ou True si on considère que l'extension LV a réussi ? False est plus sûr.

        # 3. Exécuter la commande de redimensionnement
        self.log_info(f"Exécution: {' '.join(resize_cmd)}")
        success, stdout, stderr = self.run(resize_cmd, check=False, needs_sudo=True)

        if success:
            self.log_success(f"Système de fichiers sur {lv_path} redimensionné avec succès.")
            if stdout: self.log_info(f"Sortie redimensionnement:\n{stdout}")
            return True
        else:
            self.log_error(f"Échec du redimensionnement du système de fichiers sur {lv_path}. Stderr: {stderr}")
            if stdout: self.log_info(f"Sortie redimensionnement (échec):\n{stdout}")
            return False

    # --- Commandes de Suppression ---
    # ATTENTION: Opérations destructives

    def remove_lv(self, lv_path_or_name: str) -> bool:
        """Supprime un Logical Volume."""
        full_lv_path = self._resolve_lv_path(lv_path_or_name)
        if not full_lv_path:
             self.log_error(f"Impossible de résoudre le chemin pour LV '{lv_path_or_name}'.")
             return False

        # Vérifier si monté avant suppression
        if StorageCommands(self.logger, self.target_ip).is_mounted(full_lv_path):
             self.log_error(f"Le LV '{full_lv_path}' est actuellement monté. Veuillez le démonter avant de le supprimer.")
             return False

        self.log_warning(f"Suppression du LV: {full_lv_path} - OPÉRATION DESTRUCTIVE !")
        # Utiliser -f pour forcer la suppression sans confirmation
        cmd = ['lvremove', '-f', full_lv_path]
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)
        if success:
            self.log_success(f"LV '{full_lv_path}' supprimé avec succès.")
            if stdout: self.log_info(f"Sortie lvremove:\n{stdout}")
            return True
        else:
            self.log_error(f"Échec de la suppression du LV '{full_lv_path}'. Stderr: {stderr}")
            return False

    def remove_vg(self, vg_name: str) -> bool:
        """Supprime un Volume Group (doit être vide)."""
        self.log_warning(f"Suppression du VG: {vg_name} - OPÉRATION DESTRUCTIVE (échouera si contient des LVs) !")
        # Utiliser -f pour forcer si nécessaire? Pour l'instant non.
        cmd = ['vgremove', vg_name]
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)
        if success:
            self.log_success(f"VG '{vg_name}' supprimé avec succès.")
            if stdout: self.log_info(f"Sortie vgremove:\n{stdout}")
            return True
        else:
             if "still contains" in stderr and "logical volume" in stderr:
                  self.log_error(f"Échec: Le VG '{vg_name}' contient encore des LVs. Supprimez-les d'abord.")
             else:
                  self.log_error(f"Échec de la suppression du VG '{vg_name}'. Stderr: {stderr}")
             return False

    def remove_pv(self, device: str) -> bool:
        """Supprime un Physical Volume (ne doit appartenir à aucun VG)."""
        self.log_warning(f"Suppression du PV: {device} - OPÉRATION DESTRUCTIVE (échouera s'il est utilisé par un VG) !")
        cmd = ['pvremove', '-f', '-y', device] # -f force, -y confirme
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)
        if success:
            self.log_success(f"PV '{device}' supprimé avec succès.")
            if stdout: self.log_info(f"Sortie pvremove:\n{stdout}")
            return True
        else:
             if "used by volume group" in stderr:
                  self.log_error(f"Échec: Le PV '{device}' est encore utilisé par un VG.")
             else:
                  self.log_error(f"Échec de la suppression du PV '{device}'. Stderr: {stderr}")
             return False

    # --- Fonctions Helper ---

    def _resolve_lv_path(self, lv_path_or_name: str) -> Optional[str]:
        """Tente de résoudre un nom de LV (relatif ou absolu) en chemin complet."""
        if lv_path_or_name.startswith('/dev/'):
            # Vérifier si c'est un chemin valide
            success, _, _ = self.run(['test', '-b', lv_path_or_name], check=False, no_output=True, error_as_warning=True)
            return lv_path_or_name if success else None

        # Essayer de le trouver avec lvs
        cmd = ['lvs', '--noheadings', '-o', 'lv_path', lv_path_or_name]
        success, stdout, stderr = self.run(cmd, check=False, no_output=True)
        if success and stdout.strip():
            return stdout.strip() # Retourne le chemin trouvé

        self.log_error(f"Impossible de trouver le chemin complet pour LV '{lv_path_or_name}'. Stderr: {stderr}")
        return None

