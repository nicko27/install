#!/usr/bin/env python3

import json
import netifaces
import psutil

def get_network_interfaces():
    """Récupère la liste des interfaces réseau avec leurs informations"""
    interfaces = []
    
    # Obtenir toutes les interfaces réseau
    for iface in netifaces.interfaces():
        # Ignorer l'interface loopback
        if iface == 'lo':
            continue
            
        try:
            # Obtenir les adresses de l'interface
            addrs = netifaces.ifaddresses(iface)
            
            # Obtenir les statistiques de l'interface
            stats = psutil.net_if_stats().get(iface)
            if not stats:
                continue
                
            interface_info = {
                'name': iface,
                'up': stats.isup,
                'speed': stats.speed,  # en Mbps
                'mtu': stats.mtu,
                'type': 'wireless' if iface.startswith(('wlan', 'wifi', 'wlp')) else 'ethernet'
            }
            
            # Ajouter l'adresse MAC si disponible
            if netifaces.AF_LINK in addrs:
                interface_info['mac'] = addrs[netifaces.AF_LINK][0]['addr']
            
            # Ajouter l'adresse IPv4 si disponible
            if netifaces.AF_INET in addrs:
                ipv4 = addrs[netifaces.AF_INET][0]
                interface_info.update({
                    'ipv4': ipv4['addr'],
                    'netmask': ipv4.get('netmask'),
                    'broadcast': ipv4.get('broadcast')
                })
            
            interfaces.append(interface_info)
            
        except Exception as e:
            print(f"Erreur lors de la lecture de l'interface {iface}: {e}")
            continue
    
    return interfaces

if __name__ == "__main__":
    # Afficher les interfaces au format JSON
    print(json.dumps(get_network_interfaces(), indent=2))
