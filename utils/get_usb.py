import subprocess
import json
import traceback

def get_usb(include_system_disk=False):
    """
    Récupère la liste des périphériques de stockage et leurs points de montage.
    
    Args:
        include_system_disk (bool): Si True, inclut les partitions du disque système
                                   Si False, exclut les partitions du disque système
    
    Returns:
        tuple(bool, list/str): Tuple contenant:
            - True et la liste des périphériques en cas de succès
            - False et un message d'erreur en cas d'échec
    """
    try:
        devices = []
        # Exécuter la commande lsblk pour lister les périphériques avec des informations détaillées
        result = subprocess.run(
            ['lsblk', '-o', 'NAME,SIZE,TYPE,MOUNTPOINT,PATH,FSTYPE', '-J'], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        # Vérifier si la commande a réussi
        if result.returncode != 0:
            error = f"Erreur lors de l'exécution de lsblk: {result.stderr.strip()}"
            return False, error
        
        # Analyser la sortie JSON
        devices_data = json.loads(result.stdout)
        
        # Déterminer quel est le disque système (celui qui contient la partition racine /)
        system_disks = []
        for device in devices_data.get('blockdevices', []):
            if device.get('type') == 'disk':
                for child in device.get('children', []):
                    if child.get('mountpoint') == '/':
                        system_disks.append(device.get('name', ''))
                        break
        
        # Traiter les périphériques
        for device in devices_data.get('blockdevices', []):
            # Ne traiter que les disques
            if device.get('type') == 'disk':
                # Vérifier si c'est un disque système qu'on doit exclure
                if not include_system_disk and device.get('name') in system_disks:
                    continue
                
                # Traiter les partitions du disque
                for partition in device.get('children', []):
                    if partition.get('type') == 'part':
                        device_name = partition.get('name', '')
                        path = partition.get('path', f"/dev/{device_name}")
                        size = partition.get('size', 'Inconnu')
                        mount_point = partition.get('mountpoint')
                        fs_type = partition.get('fstype', 'inconnu')
                        
                        # Créer la description formatée
                        if mount_point:
                            description = f"{path} → {mount_point} ({fs_type}, {size})"
                        else:
                            description = f"{path} → Non monté ({fs_type}, {size})"
                        
                        devices.append({
                            'device': device_name,
                            'path': path,
                            'size': size,
                            'mounted': mount_point is not None,
                            'mount_point': mount_point or '',
                            'fs_type': fs_type,
                            'description': description
                        })
        
        # Trier par nom de périphérique
        devices.sort(key=lambda x: x.get('device', '').lower())
        return True, devices
        
    except Exception as e:
        error_msg = f"Erreur lors de la récupération des périphériques: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        return False, error_msg

# Vous pouvez ajouter d'autres fonctions get_* au besoin