import os
import pwd
import grp
import traceback

def get_users(home_dir='/home'):
    print(f"[DEBUG] get_users called with home_dir={home_dir}")
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
    try:
        users = []
        # Liste uniquement les répertoires dans home_dir
        for username in os.listdir(home_dir):
            user_home = os.path.join(home_dir, username)
            if os.path.isdir(user_home):
                # Informations de base
                user_info = {
                    'username': username,
                    'home_path': user_home,
                    'description': username  # Pour l'affichage dans les menus déroulants
                }
                
                # Essayer d'obtenir des informations supplémentaires
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
                    
                    # Enrichir la description
                    if pwd_info.pw_gecos:
                        gecos_parts = pwd_info.pw_gecos.split(',')
                        full_name = gecos_parts[0] if gecos_parts else pwd_info.pw_gecos
                        if full_name and full_name != username:
                            user_info['description'] = f"{username} ({full_name})"
                except KeyError:
                    # Utilisateur non présent dans /etc/passwd
                    pass
                
                users.append(user_info)
        
        # Trier par nom d'utilisateur
        users.sort(key=lambda x: x['username'].lower())
        print(f"[DEBUG] get_users found {len(users)} users: {[u['username'] for u in users]}")
        return True, users
        
    except Exception as e:
        error_msg = f"Erreur lors de la récupération des utilisateurs: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        return False, error_msg