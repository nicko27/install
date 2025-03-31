#!/usr/bin/env python3
"""
Script wrapper pour l'exécution SSH des plugins.
Ce script est exécuté sur la machine distante et gère l'exécution du plugin avec sudo si nécessaire.
"""

import os
import sys
import json
import tempfile
import traceback
from datetime import datetime


# Ajouter le répertoire parent au chemin de recherche pour trouver les modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Configurer le répertoire de logs
def ensure_log_dir():
    # Utiliser un répertoire temporaire accessible en écriture
    log_dir = os.path.join(tempfile.gettempdir(), 'pcUtils_logs')
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
            print(f"Répertoire de logs créé: {log_dir}")
        except Exception as e:
            print(f"Erreur lors de la création du répertoire de logs: {e}")
            # Utiliser /tmp comme fallback
            log_dir = tempfile.gettempdir()

    # Définir la variable d'environnement pour que les plugins puissent trouver le répertoire de logs
    os.environ['PCUTILS_LOG_DIR'] = log_dir
    return log_dir

log_dir = ensure_log_dir()
os.environ['PCUTILS_LOG_DIR'] = log_dir
print(f"Variable d'environnement PCUTILS_LOG_DIR définie à: {log_dir}", flush=True)

# Importer les modules après avoir configuré les chemins
try:
    # Configurer les chemins d'import pour les modules du plugin
    from plugins_utils.import_helper import setup_import_paths
    setup_import_paths()

    # Importer les classes nécessaires
    from plugins_utils.plugin_logger import PluginLogger
    from plugins_utils.commands import Commands

    # Initialiser le logger pour le wrapper
    log = PluginLogger(plugin_name="ssh_wrapper", instance_id=0, ssh_mode=True)
    log.init_logs()

except ImportError as e:
    print(f"[LOG] [ERROR] Impossible d'importer les modules nécessaires: {e}")
    print(f"[LOG] [ERROR] {traceback.format_exc()}")
    sys.exit(1)

def main():
    """Fonction principale"""
    try:
        # Vérifier les arguments
        if len(sys.argv) != 2:
            log.error("Usage: python3 ssh_wrapper.py <wrapper_config_file>")
            sys.exit(1)

        wrapper_config_file = sys.argv[1]

        # Vérifier que le fichier de configuration wrapper existe
        if not os.path.exists(wrapper_config_file):
            log.error(f"Le fichier de configuration wrapper n'existe pas: {wrapper_config_file}")
            sys.exit(1)

        # Créer l'instance de commandes
        cmd = Commands(logger=log)

        # Lire la configuration du wrapper
        try:
            with open(wrapper_config_file, 'r', encoding='utf-8') as f:
                wrapper_config = json.load(f)
        except json.JSONDecodeError as e:
            log.error(f"Erreur lors de la lecture du fichier de configuration wrapper: {e}")
            sys.exit(1)

        if not wrapper_config:
            log.error("Le fichier de configuration wrapper est vide")
            sys.exit(1)

        # Récupérer les paramètres de configuration du wrapper
        plugin_path = wrapper_config.get('plugin_path')
        plugin_config = wrapper_config.get('plugin_config', {})
        needs_sudo = wrapper_config.get('needs_sudo', False)
        root_password = wrapper_config.get('root_password')

        # Récupérer les identifiants SSH depuis la configuration du plugin si disponible
        ssh_config = plugin_config.get('config', {})
        ssh_user = ssh_config.get('ssh_user')
        ssh_passwd = ssh_config.get('ssh_passwd')
        ssh_root_same = ssh_config.get('ssh_root_same', True)
        ssh_root_passwd = ssh_config.get('ssh_root_passwd')

        # Si le mot de passe root n'est pas fourni mais que ssh_root_same est True, utiliser ssh_passwd
        if not root_password and needs_sudo:
            if ssh_root_same and ssh_passwd:
                log.info("Utilisation du mot de passe SSH comme mot de passe root (ssh_root_same=true)")
                root_password = ssh_passwd
            elif ssh_root_passwd:
                log.info("Utilisation du mot de passe root spécifique depuis la configuration SSH")
                root_password = ssh_root_passwd

            if root_password:
                log.info("Mot de passe root récupéré depuis la configuration")
            else:
                log.warning("Aucun mot de passe root trouvé, sudo pourrait échouer")

        if not plugin_path:
            log.error("Chemin du plugin non spécifié dans la configuration")
            sys.exit(1)

        if not os.path.exists(plugin_path):
            log.error(f"Le script du plugin n'existe pas: {plugin_path}")
            sys.exit(1)

        # Indiquer que nous sommes en mode SSH pour le plugin
        os.environ['SSH_EXECUTION'] = '1'
        if root_password:
            os.environ['SUDO_PASSWORD'] = root_password

        # Identifier le type de plugin (bash ou python)
        is_bash_plugin = plugin_path.endswith('main.sh')

        if is_bash_plugin:
            # Pour un plugin Bash, passer les paramètres de ligne de commande
            plugin_name = plugin_config.get('plugin_name', os.path.basename(os.path.dirname(plugin_path)))
            intensity = plugin_config.get('intensity', 'light')
            run_cmd = ['bash', plugin_path, plugin_name, intensity]

            log.info(f"Exécution du plugin Bash {plugin_path} avec paramètres: {plugin_name} {intensity}")
        else:
            # Pour un plugin Python, utiliser config.json qui doit déjà être créé par ssh_executor
            config_path = os.path.join(current_dir, 'config.json')

            if not os.path.exists(config_path):
                log.error(f"Le fichier de configuration du plugin n'existe pas: {config_path}")
                sys.exit(1)

            run_cmd = ['python3', plugin_path, '-c', config_path]
            log.info(f"Exécution du plugin Python {plugin_path} avec config: {config_path}")

        # Exécuter la commande avec ou sans sudo
        if needs_sudo:
            log.info(f"Exécution avec privilèges sudo (mot de passe disponible: {'Oui' if root_password else 'Non'})")
            root_creds = {'password': root_password} if root_password else None
            if root_creds:
                log.debug("Utilisation du mot de passe root pour sudo")
                success, stdout, stderr = cmd.run_as_root(run_cmd, root_credentials=root_creds)
            else:
                log.warning("Tentative d'exécution sudo sans mot de passe (peut fonctionner si sudo est configuré sans mot de passe)")
                success, stdout, stderr = cmd.run_as_root(run_cmd)
        else:
            log.info("Exécution sans privilèges sudo")
            success, stdout, stderr = cmd.run(run_cmd)

        # Dans la section où vous vérifiez le résultat et affichez la sortie
        if success:
            if stdout and not stdout.strip().startswith('{') and not stdout.strip().startswith('['):
                # Seulement traiter la sortie si ce n'est pas déjà des logs JSON
                # Ceci évite de dupliquer les logs qui ont déjà été affichés ligne par ligne
                try:
                    # Si c'est déjà du JSON, le passer tel quel
                    json.loads(stdout)
                    print(stdout, flush=True)
                except json.JSONDecodeError:
                    # Si ce n'est pas du JSON, le convertir
                    output_entry = {
                        "timestamp": datetime.now().isoformat(),
                        "level": "info",
                        "message": stdout
                    }
                    print(json.dumps(output_entry), flush=True)
            log.success("Exécution terminée avec succès")
            sys.exit(0)
        else:
            error_entry = {
                "timestamp": datetime.now().isoformat(),
                "level": "error",
                "message": f"Erreur lors de l'exécution: {stderr}"
            }
            print(json.dumps(error_entry), flush=True)
            sys.exit(1)

    except Exception as e:
        if 'log' in locals():
            log.error(f"Erreur inattendue: {e}")
            log.error(traceback.format_exc())
        else:
            print(f"[LOG] [ERROR] Erreur inattendue dans ssh_wrapper: {e}", flush=True)
            print(f"[LOG] [ERROR] {traceback.format_exc()}", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()