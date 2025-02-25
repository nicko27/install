# Guide de Création d'un Plugin Python

Ce guide explique comment créer un plugin Python compatible avec le système d'installation.

## Structure du Plugin

```
mon_plugin/
├── settings.yml      # Configuration du plugin
├── exec.py          # Point d'entrée et logique principale
└── utils/           # Modules Python supplémentaires (optionnel)
    ├── __init__.py
    └── helpers.py
```

## 1. Configuration (settings.yml)

Le fichier `settings.yml` définit les métadonnées et la configuration du plugin :

```yaml
name: Nom du Plugin
description: Description détaillée du plugin
version: 1.0
category: Catégorie
multiple: true/false  # Si le plugin peut être exécuté plusieurs fois
icon: 🐍             # Emoji représentant le plugin

config_fields:       # Champs de configuration
  field_id:         # ID unique du champ
    type: text/select/checkbox/ip/directory  # Type de champ
    label: Label du champ
    description: Description du champ
    required: true/false
    default: Valeur par défaut
    validate: no_spaces/ip/etc  # Règles de validation
    
    # Pour les valeurs par défaut dynamiques
    dynamic_default:
      script: get_default.py
      
    # Pour les champs de type select avec options dynamiques
    options_script: get_options.py
```

## 2. Point d'Entrée (exec.py)

Le fichier principal qui contient la logique du plugin :

```python
#!/usr/bin/env python3
import os
import sys
import json
import time
import logging
from datetime import datetime

# Configuration du logging
LOG_FILE = "logs/mon_plugin.log"
formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

# Logger principal
logger = logging.getLogger('mon_plugin')
logger.setLevel(logging.DEBUG)

# Handler pour le fichier
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Handler pour la console
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

def print_progress(step: int, total: int):
    """
    Affiche la progression dans le format requis
    
    Args:
        step: Étape actuelle
        total: Nombre total d'étapes
    """
    progress = int((step * 100) / total)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [INFO] "
          f"Progression : {progress}% (étape {step}/{total})")
    sys.stdout.flush()  # Important : forcer l'envoi immédiat

def run_plugin(config: dict) -> bool:
    """
    Exécute les actions principales du plugin
    
    Args:
        config: Configuration du plugin
    
    Returns:
        bool: True si succès, False si échec
    """
    try:
        # Récupérer et valider la configuration
        param1 = config.get('param1')
        if not param1:
            logger.error("Paramètre param1 manquant")
            return False
            
        # Définir le nombre total d'étapes
        total_steps = 5
        
        # Exécuter les étapes
        for step in range(total_steps):
            current_step = step + 1
            
            # Effectuer les actions de l'étape
            logger.info(f"Exécution de l'étape {current_step}")
            
            # Simuler du travail
            time.sleep(1)
            
            # Mettre à jour la progression
            print_progress(current_step, total_steps)
            
            # Vérifier le résultat
            if not check_step_result(current_step):
                logger.error(f"Échec à l'étape {current_step}")
                return False
        
        logger.info("Plugin exécuté avec succès")
        return True
        
    except Exception as e:
        logger.exception("Erreur inattendue lors de l'exécution")
        return False

def execute_plugin(config: dict) -> tuple[bool, str]:
    """
    Point d'entrée du plugin
    
    Args:
        config: Configuration du plugin
    
    Returns:
        tuple: (succès, message)
    """
    try:
        logger.info("Démarrage du plugin")
        success = run_plugin(config)
        
        if success:
            return True, "Plugin exécuté avec succès"
        else:
            return False, "Échec de l'exécution du plugin"
            
    except Exception as e:
        logger.exception("Erreur critique")
        return False, f"Erreur critique : {str(e)}"

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: exec.py <config_json>")
        sys.exit(1)
        
    try:
        config = json.loads(sys.argv[1])
        success, message = execute_plugin(config)
        
        if success:
            print(f"Succès: {message}")
            sys.exit(0)
        else:
            print(f"Erreur: {message}")
            sys.exit(1)
            
    except json.JSONDecodeError:
        print("Erreur: Configuration JSON invalide")
        sys.exit(1)
    except Exception as e:
        print(f"Erreur inattendue: {e}")
        sys.exit(1)
```

## 3. Fonctionnalités Avancées

### Valeurs par Défaut Dynamiques

Pour un champ avec une valeur par défaut dynamique (`get_default.py`) :

```python
#!/usr/bin/env python3

def get_default_value():
    """
    Retourne la valeur par défaut
    
    Returns:
        str/dict: Valeur par défaut
    """
    # Exemple : retourner une IP
    return {
        'value': '192.168.1.1',
        'label': 'IP par défaut'
    }

if __name__ == "__main__":
    print(get_default_value())
```

### Options Dynamiques

Pour un champ select avec options dynamiques (`get_options.py`) :

```python
#!/usr/bin/env python3

def get_options():
    """
    Retourne la liste des options
    
    Returns:
        list: Liste de dictionnaires {value, label}
    """
    return [
        {'value': 'opt1', 'label': 'Option 1'},
        {'value': 'opt2', 'label': 'Option 2'}
    ]

if __name__ == "__main__":
    print(get_options())
```

## Bonnes Pratiques

1. **Progression**
   - Utiliser la fonction `print_progress`
   - Format exact : `[timestamp] [INFO] Progression : X% (étape N/M)`
   - Toujours appeler `sys.stdout.flush()` après `print`

2. **Logging**
   - Utiliser le module `logging`
   - Configurer les handlers fichier et console
   - Format : `[timestamp] [LEVEL] message`
   - Niveaux : DEBUG, INFO, WARNING, ERROR, CRITICAL

3. **Gestion des Erreurs**
   - Utiliser des blocs try/except appropriés
   - Logger les erreurs avec stack trace
   - Retourner des messages d'erreur explicites

4. **Configuration**
   - Valider tous les paramètres
   - Fournir des valeurs par défaut
   - Documenter les paramètres requis

5. **Performance**
   - Libérer les ressources (fichiers, connexions)
   - Éviter les boucles infinies
   - Gérer la mémoire efficacement

## Exemple de Configuration

```yaml
name: Mon Plugin Python
description: Plugin Python avec configuration avancée
version: 1.0
category: Installation
multiple: true
icon: 🐍
config_fields:
  server_ip:
    type: ip
    label: Adresse IP
    description: Adresse IP du serveur
    required: true
    dynamic_default:
      script: get_default_ip.py
  
  server_type:
    type: select
    label: Type de Serveur
    description: Sélectionner le type de serveur
    required: true
    options_script: get_server_types.py
  
  debug_mode:
    type: checkbox
    label: Mode Debug
    description: Activer le mode debug
    default: false
  
  log_level:
    type: select
    label: Niveau de Log
    description: Niveau de détail des logs
    enabled_if:
      field: debug_mode
      value: true
    options:
      - value: INFO
        label: Normal
      - value: DEBUG
        label: Détaillé
```
