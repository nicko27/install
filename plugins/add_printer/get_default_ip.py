import socket

def get_local_ip():
    # Crée un socket pour obtenir l'adresse IP locale
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # Essaie de se connecter à un hôte externe, mais sans envoyer de données.
        s.connect(('10.254.254.254', 1))  # Adresse IP non-routable (en dehors de ton réseau local)
        local_ip = s.getsockname()[0]     # Récupère l'adresse IP locale de l'interface
    except Exception:
        local_ip = '127.0.0.1'  # Retourne l'IP de loopback si la connexion échoue
    finally:
        s.close()
    return local_ip

if __name__ == '__main__':
    print(get_local_ip())
