import sys
import os
import glob

# Configure logging first
from ui.utils.logging import get_logger

logger = get_logger('main')
logger.info('Starting application')

# Get the absolute path to the libs folder
# Assuming main.py is at the same level as the libs folder
libs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'libs')

# Add all libs subdirectories to the search path
for pkg_dir in glob.glob(os.path.join(libs_dir, '*')):
    # Look for directories containing Python packages
    # Typically where .dist-info or .py files are stored
    for subdir in glob.glob(os.path.join(pkg_dir, '*')):
        if os.path.isdir(subdir) and (
            subdir.endswith('.dist-info') or
            os.path.exists(os.path.join(subdir, '__init__.py')) or
            subdir.endswith('.data')
        ):
            # Add the parent directory to the search path
            parent_dir = os.path.dirname(subdir)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
                logger.debug(f"Added {parent_dir} to sys.path")

        # Also add the main package directory to the path
        if pkg_dir not in sys.path:
            sys.path.insert(0, pkg_dir)
            logger.debug(f"Added {pkg_dir} to sys.path")


import argparse
from ruamel.yaml import YAML
from ui.choice_screen.choice_screen import Choice



def parse_args():
    parser = argparse.ArgumentParser(description='Install')
    parser.add_argument('--plugin', help='Exécuter directement un plugin spécifique')
    parser.add_argument('--config', help='Fichier de configuration pour le plugin')
    parser.add_argument('--params', nargs='*', help='Paramètres supplémentaires au format clé=valeur')
    
    # Options pour le mode automatisé
    parser.add_argument('--auto', action='store_true', help='Mode automatisé : exécution directe')
    parser.add_argument('--sequence', help='Fichier de séquence à exécuter')
    parser.add_argument('--output-dir', default='rapports', help='Dossier pour les rapports')
    parser.add_argument('--remote', help='Exécution sur machine distante (format: user@host)')
    parser.add_argument('--show-all', action='store_true', help='Afficher les résultats de toutes les machines')
    
    # Options pour les rapports
    parser.add_argument('--no-report', action='store_true', help='Désactiver la génération des rapports')
    parser.add_argument('--view-report', help='Visualiser un rapport ou dossier de rapports')
    parser.add_argument('--report-format', choices=['csv', 'txt'], default='csv', 
                        help='Format du rapport (défaut: csv)')
    
    return parser.parse_args()

def load_config(config_file):
    if not config_file:
        return {}
    yaml=YAML()
    try:
        with open(config_file, 'r') as f:
            return yaml.load(f)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return {}

def parse_params(params):
    if not params:
        return {}
    config = {}
    for param in params:
        try:
            key, value = param.split('=')
            config[key.strip()] = value.strip()
        except ValueError:
            print(f"Invalid format for parameter: {param}. Use key=value")
    return config

def setup_output_directory(output_dir):
    """Crée le dossier de sortie pour les rapports"""
    try:
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"Dossier de rapports créé : {output_dir}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la création du dossier de rapports : {e}")
        return False

def get_machine_name():
    """Récupère le nom de la machine locale"""
    try:
        import socket
        return socket.gethostname()
    except:
        return "unknown_host"

def copy_report_from_remote(remote, local_path):
    """Copie les rapports depuis une machine distante"""
    try:
        import subprocess
        cmd = ["scp", f"{remote}:{local_path}", local_path]
        subprocess.run(cmd, check=True)
        logger.info(f"Rapport récupéré depuis {remote}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du rapport distant : {e}")
        return False

if __name__ == "__main__":
    args = parse_args()

    # Visualisation d'un rapport existant
    if args.view_report:
        from ui.report_screen import ReportScreen
        from textual.app import App
        
        class ReportApp(App):
            """Application pour visualiser les rapports"""
            
            def on_mount(self) -> None:
                """Monter l'écran de rapport"""
                self.push_screen(ReportScreen(args.view_report))
        
        app = ReportApp()
        app.run()
        sys.exit(0)

    # Mode automatisé
    if args.auto:
        if not args.sequence:
            logger.error("Le mode automatisé nécessite un fichier de séquence (--sequence)")
            sys.exit(1)

        # Préparer le dossier de rapports
        if not setup_output_directory(args.output_dir):
            sys.exit(1)

        # Nom du fichier de rapport basé sur la machine et la date
        machine_name = get_machine_name()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if not args.no_report:
            if args.report_format == 'csv':
                report_file = os.path.join(args.output_dir, f"rapport_{machine_name}_{timestamp}.csv")
            else:
                report_file = os.path.join(args.output_dir, f"rapport_{machine_name}_{timestamp}.txt")
        else:
            report_file = None

        # Exécuter la séquence en mode automatisé
        app = Choice()
        app.sequence_file = args.sequence
        app.auto_execute = True
        app.report_file = report_file
        app.report_format = args.report_format
        app.run()

        # Si exécution distante, récupérer le rapport
        if args.remote and report_file:
            copy_report_from_remote(args.remote, report_file)

        # Afficher les résultats si demandé
        if args.show_all and report_file:
            from ui.report_screen import ReportScreen
            from textual.app import App
            
            class ReportApp(App):
                """Application pour visualiser les rapports"""
                
                def on_mount(self) -> None:
                    """Monter l'écran de rapport"""
                    self.push_screen(ReportScreen(args.output_dir))
            
            app = ReportApp()
            app.run()

    # Exécution directe d'un plugin
    elif args.plugin:
        config = {}
        if args.config:
            config.update(load_config(args.config))
        if args.params:
            config.update(parse_params(args.params))

        plugins_config = {args.plugin: config}
        
        # Configurer le gestionnaire de rapports si nécessaire
        report_manager = None
        if not args.no_report:
            from ui.report_screen.report_manager import ReportManager
            report_manager = ReportManager(args.output_dir if args.output_dir else 'rapports')
        
        from ui.execution_screen.execution_screen import ExecutionScreen
        from textual.app import App
        
        class ExecutionApp(App):
            """Application pour l'exécution des plugins"""
            
            def on_mount(self) -> None:
                """Monter l'écran d'exécution"""
                self.push_screen(ExecutionScreen(plugins_config, False, report_manager))
                
            async def on_execution_screen_show_report_requested(self, message) -> None:
                """Gérer la demande d'affichage du rapport"""
                from ui.report_screen import ReportScreen
                self.push_screen(ReportScreen(message.report_path))
        
        app = ExecutionApp()
        app.run()

    # Interface normale
    else:
        app = Choice()
        app.run()
