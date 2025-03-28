"""
Module pour le traitement automatique d'une configuration de séquence sans interface graphique.
"""

import os
import traceback
from ruamel.yaml import YAML
import json

from ..utils.logging import get_logger
from ..choice_screen.plugin_utils import get_plugin_folder_name
from .config_manager import ConfigManager

logger = get_logger('auto_config')
yaml = YAML()
yaml.preserve_quotes = True

class AutoConfig:
    """
    Gestion automatique de la configuration des plugins sans interface graphique.
    Cette classe permet de traiter une séquence et de générer une configuration
    compatible avec ExecutionScreen sans passer par l'interface de configuration.
    """
    
    def __init__(self):
        """Initialisation du gestionnaire de configuration automatique."""
        logger.debug("Initialisation d'AutoConfig")
        self.config_manager = ConfigManager()
        
    def process_sequence(self, sequence_path, plugin_instances):
        """
        Traite une séquence et génère une configuration pour tous les plugins.
        
        Args:
            sequence_path (str): Chemin vers le fichier de séquence YAML
            plugin_instances (list): Liste de tuples (plugin_name, instance_id)
            
        Returns:
            dict: Configuration des plugins au format attendu par ExecutionScreen
        """
        try:
            logger.debug(f"Traitement de la séquence {sequence_path} avec {len(plugin_instances)} plugins")
            
            # Charger la séquence
            sequence_data = None
            try:
                with open(sequence_path, 'r') as f:
                    sequence_data = yaml.load(f)
                logger.debug(f"Séquence chargée: {sequence_path}")
            except Exception as e:
                logger.error(f"Erreur chargement séquence: {e}")
                return {}
            
            # Configuration finale à retourner
            config = {}
            
            # Traiter chaque plugin
            for plugin_name, instance_id in plugin_instances:
                plugin_id = f"{plugin_name}_{instance_id}"
                logger.debug(f"Traitement du plugin {plugin_id}")
                
                # Chercher la configuration du plugin dans la séquence
                plugin_config = None
                matching_plugins = [p for p in sequence_data.get('plugins', []) 
                                 if p.get('name') == plugin_name and isinstance(p, dict)]
                
                if instance_id < len(matching_plugins):
                    p = matching_plugins[instance_id]
                    # Récupérer la configuration du plugin
                    plugin_config = p.get('config', {})
                    if not plugin_config:
                        # Compatibilité avec l'ancien format
                        plugin_config = {k: v for k, v in p.items() if k != 'name'}
                    logger.debug(f"Configuration trouvée pour {plugin_name} instance {instance_id}")
                
                if not plugin_config:
                    logger.warning(f"Configuration non trouvée pour {plugin_name}")
                    continue
                
                # Charger les paramètres du plugin
                folder_name = get_plugin_folder_name(plugin_name)
                settings_path = os.path.join(os.path.dirname(__file__), '..', '..', 'plugins', folder_name, 'settings.yml')
                plugin_settings = {}
                
                try:
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        plugin_settings = yaml.load(f)
                    logger.debug(f"Paramètres chargés pour {plugin_name}")
                except Exception as e:
                    logger.error(f"Erreur lors du chargement des paramètres de {plugin_name}: {e}")

                # Vérifier si c'est un plugin SSH
                if 'ssh_ips' in plugin_config:
                    # Gérer les IPs multiples ou wildcards
                    from ..ssh_manager.ip_utils import get_target_ips
                    target_ips = get_target_ips(plugin_config.get('ssh_ips', ''), plugin_config.get('ssh_exception_ips', []))
                    if target_ips:
                        plugin_config['ssh_ips'] = ','.join(target_ips)
                
                # Vérifier si le plugin utilise files_content
                files_content = {}
                if 'files_content' in plugin_settings and isinstance(plugin_settings['files_content'], dict):
                    files_content = plugin_settings['files_content']
                    logger.debug(f"Le plugin {plugin_name} utilise files_content: {files_content}")
                
                # Ajouter la configuration au dictionnaire final
                config[plugin_id] = plugin_config
                logger.debug(f"Configuration ajoutée pour {plugin_id}: {plugin_config}")
                
                # Charger le contenu des fichiers dynamiques si nécessaire
                for content_key, path_template in files_content.items():
                    try:
                        # Remplacer les variables dans le chemin
                        import re
                        variables = re.findall(r'\{([^}]+)\}', path_template)
                        
                        if not variables:
                            logger.debug(f"Aucune variable trouvée dans {path_template}")
                            continue
                        
                        # Récupérer les valeurs des variables depuis plugin_config
                        file_path = path_template
                        for var in variables:
                            if var in plugin_config:
                                file_path = file_path.replace(f"{{{var}}}", str(plugin_config[var]))
                            else:
                                logger.warning(f"Variable {var} non trouvée dans la configuration")
                                break
                        
                        # Si toutes les variables sont remplacées, charger le fichier
                        if '{' not in file_path:
                            # Construire le chemin complet
                            full_path = os.path.join(os.path.dirname(__file__), '..', '..', 'plugins', folder_name, file_path)
                            
                            if os.path.exists(full_path):
                                # Charger le contenu du fichier
                                with open(full_path, 'r', encoding='utf-8') as f:
                                    file_content = yaml.load(f)
                                
                                # Ajouter le contenu à plugin_config
                                plugin_config[content_key] = file_content
                                logger.debug(f"Contenu de {full_path} chargé pour {content_key}")
                            else:
                                logger.warning(f"Fichier {full_path} introuvable")
                    except Exception as e:
                        logger.error(f"Erreur lors du chargement de {content_key}: {e}")
                        logger.error(traceback.format_exc())
                
                # Vérifier si le plugin supporte l'exécution distante
                supports_remote = plugin_settings.get('remote_execution', False)
                remote_enabled = plugin_config.get('remote_execution', False)
                
                # Construire la configuration finale pour ce plugin
                config[plugin_id] = {
                    'plugin_name': plugin_name,
                    'instance_id': instance_id,
                    'name': plugin_settings.get('name', plugin_name),
                    'show_name': plugin_settings.get('plugin_name', plugin_name),
                    'icon': plugin_settings.get('icon', '📦'),
                    'config': plugin_config,
                    'remote_execution': supports_remote and remote_enabled
                }
                
                logger.debug(f"Configuration générée pour {plugin_id}")
            
            logger.debug(f"Configuration complète générée avec {len(config)} plugins")
            return config
            
        except Exception as e:
            logger.error(f"Erreur lors du traitement de la séquence: {e}")
            logger.error(traceback.format_exc())
            return {}

# Fonction utilitaire pour être appelée directement depuis main.py
def process_sequence_file(sequence_path, plugin_instances):
    """
    Traite un fichier de séquence et retourne la configuration des plugins.
    
    Args:
        sequence_path (str): Chemin vers le fichier de séquence
        plugin_instances (list): Liste de tuples (plugin_name, instance_id)
        
    Returns:
        dict: Configuration des plugins au format ExecutionScreen
    """
    auto_config = AutoConfig()
    return auto_config.process_sequence(sequence_path, plugin_instances) 