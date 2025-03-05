import os
import pwd
import grp
import traceback
from typing import Tuple, List, Dict, Union, Any

# Utiliser un chemin absolu pour l'importation
import sys
import os.path

# Obtenir le chemin absolu du répertoire parent
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ajouter le répertoire parent au chemin de recherche Python
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Importer le module de logging
try:
    from utils.logging import get_logger
    logger = get_logger('get_users')
except ImportError as e:
    # Fallback en cas d'erreur d'importation
    import logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger('get_users')
    logger.error(f"Erreur d'importation du module de logging: {e}")

def get_users(home_dir: str = '/home') -> Tuple[bool, Union[List[Dict[str, Any]], str]]:
    """
    Récupère la liste des utilisateurs à partir d'un répertoire home spécifique.
    
    Args:
        home_dir (str): Chemin du répertoire contenant les dossiers des utilisateurs
                       Par défaut : '/home'
    
    Returns:
        tuple(bool, list/str): Tuple contenant:
            - True et la liste des utilisateurs en cas de succès
            - False et un message d'erreur en cas d'échec
    """
    logger.debug(f"get_users called with home_dir={home_dir}")
    logger.debug(f"Script path: {__file__}")
    logger.debug(f"Current working directory: {os.getcwd()}")
    
    # Vérifier que le répertoire home existe
    if not os.path.exists(home_dir):
        error_msg = f"Le répertoire {home_dir} n'existe pas"
        logger.error(error_msg)
        return False, error_msg
    
    if not os.path.isdir(home_dir):
        error_msg = f"{home_dir} n'est pas un répertoire"
        logger.error(error_msg)
        return False, error_msg
    
    try:
        users = []
        # Liste uniquement les répertoires dans home_dir
        for username in os.listdir(home_dir):
            user_home = os.path.join(home_dir, username)
            
            # Ignorer les fichiers et les liens symboliques
            if not os.path.isdir(user_home):
                continue
                
            # Ignorer les dossiers cachés (commençant par un point)
            if username.startswith('.'):
                continue
            
            # Informations de base
            user_info = {
                'username': username,
                'home_path': user_home,
                'description': username  # Valeur par défaut pour l'affichage
            }
            
            # Essayer d'obtenir des informations supplémentaires du système
            try:
                pwd_info = pwd.getpwnam(username)
                user_info['uid'] = pwd_info.pw_uid
                user_info['gid'] = pwd_info.pw_gid
                user_info['shell'] = pwd_info.pw_shell
                
                # Informations sur le groupe principal
                try:
                    group_info = grp.getgrgid(pwd_info.pw_gid)
                    user_info['group'] = group_info.gr_name
                except KeyError:
                    user_info['group'] = str(pwd_info.pw_gid)
                
                # Enrichir la description avec le nom complet si disponible
                if pwd_info.pw_gecos:
                    gecos_parts = pwd_info.pw_gecos.split(',')
                    full_name = gecos_parts[0] if gecos_parts else pwd_info.pw_gecos
                    if full_name and full_name != username:
                        user_info['description'] = f"{username} ({full_name})"
            except KeyError:
                # L'utilisateur existe sur le disque mais pas dans /etc/passwd
                # C'est normal dans certains cas (ex: utilisateurs d'un autre système)
                logger.debug(f"Utilisateur {username} trouvé sur le disque mais absent de /etc/passwd")
            
            users.append(user_info)
        
        # Trier par nom d'utilisateur (insensible à la casse)
        users.sort(key=lambda x: x['username'].lower())
        
        logger.debug(f"get_users found {len(users)} users: {[u['username'] for u in users]}")
        
        return True, users
        
    except PermissionError:
        error_msg = f"Permission refusée pour accéder au répertoire {home_dir}"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Erreur lors de la récupération des utilisateurs: {str(e)}"
        logger.error(error_msg)
        logger.debug(traceback.format_exc())
        return False, error_msg