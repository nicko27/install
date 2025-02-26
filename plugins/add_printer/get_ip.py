import socket

def get_local_ip():
    # Crée un socket pour obtenir l'adresse IP locale
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # Essaie de se connecter à un hôte externe, mais sans envoyer de données.
        s.connect(('10.254.254.254', 1))  # Adresse IP non-routable (en dehors de ton réseau local)
        local_ip = s.getsockname()[0]     # Récupère l'adresse IP locale de l'interface
        octet_1,octet_2,octet_3,octet_4 = local_ip.split('.')
        if octet_1 == '128' and octet_2 == '81' and octet_3 in ['2','3']:
            local_ip = '128.81.2.184'
        elif octet_1 == '128' and octet_2 == '81' and octet_3 in ['4','5']:
            local_ip = '128.81.4.184'
        else:
            local_ip = f"{octet_1}.{octet_2}.{octet_3}.220"
    except Exception:
        local_ip = '128.81.2.220'  # Retourne l'IP de loopback si la connexion échoue
    finally:
        s.close()
    return local_ip

