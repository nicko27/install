# install/plugins/plugins_utils/system_info_extended.py
#!/usr/bin/env python3
"""
Module utilitaire pour récupérer des informations système et matérielles étendues.
Utilise des commandes comme lspci, lsusb, dmidecode, hdparm, smartctl.
"""

from plugins_utils.plugins_utils_base import PluginsUtilsBase
import os
import re
import json
from typing import Union, Optional, List, Dict, Any, Tuple

class SystemInfoExtended(PluginsUtilsBase):
    """
    Classe pour récupérer des informations système et matérielles détaillées.
    Hérite de PluginUtilsBase pour l'exécution de commandes.
    """

    def __init__(self, logger=None, target_ip=None):
        """Initialise le gestionnaire d'informations étendues."""
        super().__init__(logger, target_ip)
        # Vérifier la présence des commandes nécessaires

    def get_pci_devices(self) -> List[Dict[str, str]]:
        """
        Liste les périphériques PCI détectés par le système.

        Returns:
            Liste de dictionnaires, chaque dict représentant un périphérique PCI.
            Clés communes: 'slot', 'class', 'vendor', 'device', 'subvendor', 'subdevice', 'revision'.
        """
        self.log_info("Récupération des informations sur les périphériques PCI (lspci)")
        # Utiliser -mm pour un format machine facile à parser
        # Utiliser -vnn pour obtenir les IDs numériques et les noms verbeux
        success, stdout, stderr = self.run(['lspci', '-mm', '-vnn'], check=False, no_output=True)
        devices = []
        if not success:
            self.log_error(f"Échec de la commande lspci. Stderr: {stderr}")
            return devices

        current_device: Dict[str, str] = {}
        for line in stdout.splitlines():
            line = line.strip()
            if not line: # Ligne vide sépare les périphériques
                if current_device:
                    devices.append(current_device)
                current_device = {}
                continue

            # Format: Key:\tValue
            if ":\t" in line:
                key, value = line.split(":\t", 1)
                key_norm = key.strip().lower().replace(' ', '_')
                # Extraire les IDs numériques et les noms si présents (ex: Vendor [1234])
                match = re.match(r'(.*) \[([0-9a-fA-Fx]+)\]', value)
                if match:
                    current_device[key_norm + '_name'] = match.group(1).strip()
                    current_device[key_norm + '_id'] = match.group(2).strip()
                else:
                    current_device[key_norm] = value.strip()
            else:
                # Gérer les cas où la clé n'est pas présente (rare)
                if 'unknown_property' not in current_device:
                    current_device['unknown_property'] = []
                current_device['unknown_property'].append(line)


        # Ajouter le dernier périphérique
        if current_device:
            devices.append(current_device)

        self.log_info(f"{len(devices)} périphériques PCI trouvés.")
        self.log_debug(f"Données PCI: {devices}")
        return devices

    def get_usb_devices(self, verbose: bool = False) -> List[Dict[str, str]]:
        """
        Liste les périphériques USB détectés.

        Args:
            verbose: Si True, utilise 'lsusb -v' pour des détails (parsing complexe).
                     Si False (défaut), utilise 'lsusb' simple (moins de détails).

        Returns:
            Liste de dictionnaires représentant les périphériques USB.
        """
        self.log_info(f"Récupération des informations sur les périphériques USB (lsusb {'-v' if verbose else ''})")
        cmd = ['lsusb']
        if verbose:
            cmd.append('-v')
            # lsusb -v nécessite souvent root
            needs_sudo_flag = True
        else:
            needs_sudo_flag = False # lsusb simple n'a généralement pas besoin de root

        # Exécuter lsusb
        success, stdout, stderr = self.run(cmd, check=False, no_output=True, needs_sudo=needs_sudo_flag)
        devices = []
        if not success:
            self.log_error(f"Échec de la commande lsusb. Stderr: {stderr}")
            return devices

        if verbose:
            # --- Parsing de 'lsusb -v' ---
            # C'est complexe et sujet aux erreurs. Un exemple simplifié :
            current_device = None
            for line in stdout.splitlines():
                line = line.strip()
                if line.startswith("Bus "):
                    if current_device: devices.append(current_device)
                    # Format: Bus XXX Device YYY: ID VENDOR:PRODUCT NAME
                    match = re.match(r"Bus (\d+) Device (\d+): ID ([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)", line)
                    if match:
                        current_device = {
                            'bus': match.group(1),
                            'device_addr': match.group(2),
                            'vendor_id': match.group(3),
                            'product_id': match.group(4),
                            'description': match.group(5).strip()
                        }
                    else: current_device = {} # Erreur de parsing ligne Bus
                elif current_device and ':' in line:
                    # Parser les attributs clés : valeur
                    key, value = line.split(':', 1)
                    key_norm = key.strip().lower().replace(' ', '_')
                    # Simplification: ne stocker que quelques clés utiles
                    if key_norm in ['idevmanufacturer', 'idproduct', 'iserial']:
                         # Extraire la valeur après le numéro d'index potentiel
                         parts = value.strip().split(None, 1)
                         current_device[key_norm] = parts[-1] if parts else ''

            if current_device: devices.append(current_device)

        else:
            # --- Parsing de 'lsusb' simple ---
            # Format: Bus XXX Device YYY: ID VENDOR:PRODUCT NAME
            for line in stdout.splitlines():
                match = re.match(r"Bus (\d+) Device (\d+): ID ([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)", line)
                if match:
                    devices.append({
                        'bus': match.group(1),
                        'device_addr': match.group(2),
                        'id': f"{match.group(3)}:{match.group(4)}",
                        'vendor_id': match.group(3),
                        'product_id': match.group(4),
                        'description': match.group(5).strip()
                    })

        self.log_info(f"{len(devices)} périphériques USB trouvés.")
        self.log_debug(f"Données USB: {devices}")
        return devices

    def get_dmi_info(self) -> Dict[str, Any]:
        """
        Récupère les informations DMI/SMBIOS via dmidecode. Nécessite root.

        Returns:
            Dictionnaire structuré avec les informations DMI (System, Base Board, BIOS, etc.).
        """
        self.log_info("Récupération des informations DMI/SMBIOS (dmidecode)")
        # dmidecode nécessite root
        success, stdout, stderr = self.run(['dmidecode'], check=False, no_output=True, needs_sudo=True)
        dmi_data: Dict[str, Any] = {}
        if not success:
            self.log_error(f"Échec de la commande dmidecode. Stderr: {stderr}")
            return dmi_data

        current_section_handle = None
        current_section_data: Optional[Dict[str, Any]] = None
        section_name = "Unknown Section"

        for line in stdout.splitlines():
            line_strip = line.strip()
            if not line_strip: continue

            # Détecter une nouvelle section
            if line.startswith("Handle 0x"):
                # Sauvegarder la section précédente
                if current_section_data and current_section_handle:
                    section_key = f"{section_name.replace(' ', '')}_{current_section_handle}"
                    if section_key not in dmi_data:
                         dmi_data[section_key] = current_section_data
                    else: # Gérer les handles dupliqués (rare)
                         dmi_data[f"{section_key}_alt"] = current_section_data

                # Commencer la nouvelle section
                parts = line.split(',')
                current_section_handle = parts[0].split()[-1] # Handle 0xABCD -> ABCD
                current_section_data = {}
                section_name = "Unknown Section" # Réinitialiser
                if len(parts) > 1:
                     section_name = parts[1].strip().replace(" Information", "") # Ex: "BIOS Information" -> "BIOS"
                current_section_data['_type'] = section_name
                continue

            # Parser les informations dans la section
            if current_section_data is not None and line.startswith('\t'):
                line_content = line.strip()
                if ':' in line_content:
                    key, value = line_content.split(':', 1)
                    key_norm = key.strip().lower().replace(' ', '_')
                    current_section_data[key_norm] = value.strip()
                # Gérer les listes (comme Characteristics ou Options)
                elif current_section_data and '_type' in current_section_data:
                    list_key = current_section_data['_type'].lower() + "_options" # ex: bios_options
                    if list_key not in current_section_data:
                        current_section_data[list_key] = []
                    current_section_data[list_key].append(line_content)

        # Ajouter la dernière section
        if current_section_data and current_section_handle:
             section_key = f"{section_name.replace(' ', '')}_{current_section_handle}"
             if section_key not in dmi_data:
                  dmi_data[section_key] = current_section_data
             else:
                  dmi_data[f"{section_key}_alt"] = current_section_data

        self.log_info("Informations DMI récupérées.")
        self.log_debug(f"Données DMI: {json.dumps(dmi_data, indent=2)}") # Utiliser json pour lisibilité
        return dmi_data

    def get_disk_details(self, device: str) -> Dict[str, str]:
        """
        Récupère des détails sur un disque (modèle, série, vendor) via lsblk.

        Args:
            device: Chemin du périphérique (ex: /dev/sda).

        Returns:
            Dictionnaire avec les détails trouvés.
        """
        dev_name = os.path.basename(device)
        self.log_info(f"Récupération des détails du disque {dev_name} (lsblk)")
        # Utiliser -d pour ne montrer que le disque, pas les partitions
        # Utiliser -n pour ne pas afficher l'en-tête
        # Utiliser -o pour spécifier les colonnes
        cmd = ['lsblk', '-d', '-n', '-o', 'NAME,MODEL,SERIAL,VENDOR,SIZE,TYPE,TRAN', device]
        success, stdout, stderr = self.run(cmd, check=False, no_output=True)
        details = {'device': dev_name}
        if not success:
            self.log_error(f"Échec de lsblk pour {device}. Stderr: {stderr}")
            return details

        # Format: NAME MODEL SERIAL VENDOR SIZE TYPE TRAN
        parts = stdout.strip().split(None, 6) # Split max 6 fois
        keys = ['name_lsblk', 'model', 'serial', 'vendor', 'size', 'type', 'transport']
        if len(parts) == len(keys):
            details.update(dict(zip(keys, parts)))
        else:
             self.log_warning(f"Format de sortie lsblk inattendu pour {device}: {stdout}")

        self.log_debug(f"Détails lsblk pour {dev_name}: {details}")
        return details

    def get_disk_smart_info(self, device: str) -> Optional[Dict[str, Any]]:
        """
        Récupère les informations SMART d'un disque via smartctl. Nécessite root.

        Args:
            device: Chemin du périphérique (ex: /dev/sda).

        Returns:
            Dictionnaire avec les attributs SMART ou None si échec/non supporté.
        """
        dev_name = os.path.basename(device)
        self.log_info(f"Récupération des informations SMART pour {dev_name} (smartctl)")
        # -a : toutes les infos SMART
        # -j : sortie JSON
        cmd = ['smartctl', '-a', '-j', device]
        success, stdout, stderr = self.run(cmd, check=False, no_output=True, needs_sudo=True)

        if not success:
            if "Unavailable - device interface logic possibly hung" in stderr:
                 self.log_warning(f"Impossible de lire les infos SMART pour {dev_name} (périphérique potentiellement suspendu?).")
            elif "Device open changed type from" in stderr:
                 self.log_warning(f"Type de périphérique changé pour {dev_name} pendant la lecture SMART.")
            elif "Unknown USB bridge" in stderr:
                 self.log_warning(f"Pont USB non supporté pour SMART sur {dev_name}. Essayer avec -d sat ou -d usb* ?")
            elif "NVMe Status 0x2002" in stderr: # Common NVMe error if not supported well
                 self.log_warning(f"Erreur NVMe Status 0x2002 pour {dev_name}.")
            elif "Read Device Identity failed" in stderr:
                 self.log_warning(f"Échec de lecture de l'identité SMART pour {dev_name}.")
            elif "Unavailable - skipping device" in stderr:
                 self.log_warning(f"Périphérique {dev_name} indisponible pour SMART.")
            else:
                 self.log_error(f"Échec de smartctl pour {dev_name}. Stderr: {stderr}")
            return None

        try:
            smart_data = json.loads(stdout)
            self.log_info(f"Informations SMART récupérées pour {dev_name}.")
            # Retourner seulement les parties utiles ? Ou tout ? Retourner tout pour l'instant.
            # Exemple de clés utiles: smart_status['passed'], temperature['current'], ata_smart_attributes['table']
            self.log_debug(f"Données SMART pour {dev_name}: {json.dumps(smart_data, indent=2)}")
            return smart_data
        except json.JSONDecodeError as e:
            self.log_error(f"Erreur de parsing JSON pour la sortie smartctl de {dev_name}: {e}")
            self.log_debug(f"Sortie smartctl brute:\n{stdout}")
            return None
        except Exception as e:
            self.log_error(f"Erreur inattendue lors du traitement des données SMART de {dev_name}: {e}", exc_info=True)
            return None

    def get_cpu_flags(self) -> List[str]:
        """Récupère la liste des flags du premier CPU listé dans /proc/cpuinfo."""
        self.log_debug("Lecture des flags CPU depuis /proc/cpuinfo")
        flags = []
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.strip().startswith('flags'):
                        flags = line.split(':', 1)[1].strip().split()
                        break # Prendre les flags du premier CPU
            self.log_debug(f"Flags CPU trouvés: {len(flags)}")
        except Exception as e:
            self.log_error(f"Erreur lors de la lecture de /proc/cpuinfo: {e}")
        return flags

