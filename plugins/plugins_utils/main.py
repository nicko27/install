import argparse
import sys
import json
import traceback
import time

def main(log,plugin):
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument('-c', '--config', help='Fichier de configuration JSON')
        parser.add_argument('json_config', nargs='?', help='Configuration JSON en ligne de commande')
        args, unknown = parser.parse_known_args()

        if args.config:
            # Lire la configuration depuis le fichier (mode SSH)
            with open(args.config, 'r', encoding='utf-8') as f:
                config = json.load(f)
        elif args.json_config:
            # Charger la configuration depuis l'argument positionnelle (mode local)
            config = json.loads(args.json_config)
        elif len(sys.argv) > 1 and sys.argv[1].startswith('{'):
            # Fallback: essayer de parser le premier argument comme JSON
            config = json.loads(sys.argv[1])
        else:
            raise ValueError("Aucune configuration fournie. Utilisez -c/--config ou passez un JSON en argument.")

        # Initialiser le logger
        log.plugin_name = config.get("plugin_name", "add_printer")
        log.instance_id = config.get("instance_id", 0)
        if config.get("ssh_mode", False):
            log.ssh_mode = True
            log.init_logs()

        # Vérifier si la configuration est correcte
        if 'config' not in config:
            # Pour la compatibilité avec l'exécution locale, créer la structure attendue
            # si elle n'existe pas déjà
            plugin_config = {}
            for key, value in config.items():
                if key not in ["plugin_name", "instance_id", "ssh_mode"]:
                    plugin_config[key] = value

            # Reconstruire la configuration avec la structure attendue
            config = {
                "plugin_name": config.get("plugin_name", "add_printer"),
                "instance_id": config.get("instance_id", 0),
                "ssh_mode": config.get("ssh_mode", False),
                "config": plugin_config
            }

            log.debug(f"Configuration restructurée pour compatibilité: {json.dumps(config, indent=2)}")

        # Exécuter le plugin
        success, message = plugin.execute_plugin(config)

        # Attendre un court instant pour s'assurer que tous les logs sont traités
        time.sleep(0.2)

        # Afficher le résultat final
        if success:
            log.success(f"Succès: {message}")
            sys.exit(0)
        else:
            log.error(f"Échec: {message}")
            sys.exit(1)

    except json.JSONDecodeError as je:
        log.error("Erreur: Configuration JSON invalide")
        sys.exit(1)
    except Exception as e:
        log.error(f"Erreur inattendue: {e}")
        log.debug(traceback.format_exc())
        sys.exit(1)