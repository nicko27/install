#!/usr/bin/env python3
import socket
import json
import netifaces

def get_default_ip():
    # Liste des préfixes d'interface à vérifier dans l'ordre
    interface_prefixes = ['eth', 'enp', 'wlan', 'wlp']
    
    try:
        # Récupérer toutes les interfaces
        interfaces = netifaces.interfaces()
        
        # Chercher une interface dans l'ordre de préférence
        for prefix in interface_prefixes:
            for iface in interfaces:
                if iface.startswith(prefix):
                    addrs = netifaces.ifaddresses(iface)
                    if netifaces.AF_INET in addrs:  # IPv4
                        for addr in addrs[netifaces.AF_INET]:
                            ip = addr['addr']
                            if not ip.startswith('127.'):
                                # Construire l'IP de l'imprimante
                                base_ip = '.'.join(ip.split('.')[:-1])
                                return {"value": f"{base_ip}.220"}
        
        # Si aucune interface trouvée, utiliser une IP locale
        return {"value": "192.168.1.220"}
                                
    except Exception as e:
        print(f"Erreur: {e}")
        return {"value": "192.168.1.220"}

if __name__ == '__main__':
    print(get_default_ip())
