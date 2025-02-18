# Guide de Création d'un Plugin Bash

Ce guide explique comment créer un plugin Bash compatible avec le système d'installation.

## Structure du Plugin

```
mon_plugin/
├── settings.yml      # Configuration du plugin
├── exec.py          # Point d'entrée Python
└── main.sh          # Script Bash principal
```

## 1. Configuration (settings.yml)

Le fichier `settings.yml` définit les métadonnées et la configuration du plugin :

```yaml
name: Nom du Plugin
description: Description détaillée du plugin
version: 1.0
category: Catégorie
multiple: true/false  # Si le plugin peut être exécuté plusieurs fois
icon: 🔧             # Emoji représentant le plugin

config_fields:       # Champs de configuration
  field_id:         # ID unique du champ
    type: text/select/checkbox/ip/directory  # Type de champ
    label: Label du champ
    description: Description du champ
    required: true/false
    default: Valeur par défaut
    validate: no_spaces/ip/etc  # Règles de validation
    placeholder: Exemple de valeur
    
    # Pour les champs de type select
    options:
      - value: valeur1
        label: Label 1
      - value: valeur2
        label: Label 2
```

## 2. Point d'Entrée (exec.py)

Le fichier `exec.py` gère l'exécution du script Bash :

```python
#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import logging

def execute_plugin(config):
    """
    Point d'entrée pour l'exécution du plugin
    
    Args:
        config (dict): Configuration du plugin
        
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        # Récupérer les paramètres de configuration
        param1 = config.get('param1', 'default')
        
        # Chemin du script bash
        bash_script = os.path.join(os.path.dirname(__file__), 'main.sh')
        
        # Rendre le script exécutable
        subprocess.run(['chmod', '+x', bash_script], check=True)
        
        # Exécuter le script bash
        result = subprocess.run(
            [bash_script, param1], 
            capture_output=True, 
            text=True
        )
        
        # Vérifier le code de retour
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, result.stderr.strip()
            
    except Exception as e:
        logging.exception(f"Erreur lors de l'exécution du plugin")
        return False, f"Erreur d'exécution : {str(e)}"

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
    except Exception as e:
        print(f"Erreur inattendue: {e}")
        sys.exit(1)
```

## 3. Script Bash (main.sh)

Le script Bash qui effectue les actions du plugin :

```bash
#!/bin/bash

# Fonction pour afficher la progression
# Format requis: [timestamp] [INFO] Progression : X% (étape N/M)
print_progress() {
    local step=$1
    local total=$2
    local progress=$((step * 100 / total))
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] Progression : $progress% (étape $step/$total)"
}

# Récupérer les arguments
param1="$1"

# Nombre total d'étapes
total_steps=5

# Exécution des étapes
for ((step=1; step<=total_steps; step++)); do
    # Afficher la progression
    print_progress "$step" "$total_steps"
    
    # Simuler du travail
    sleep 1
    
    # En cas d'erreur
    if [ $? -ne 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] Erreur à l'étape $step" >&2
        exit 1
    fi
done

# Succès
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] Opération terminée avec succès"
exit 0
```

## Bonnes Pratiques

1. **Progression**
   - Utiliser le format exact : `[timestamp] [INFO] Progression : X% (étape N/M)`
   - Mettre à jour la progression régulièrement
   - Utiliser `echo` pour envoyer la progression sur stdout

2. **Logs**
   - Utiliser le format : `[timestamp] [LEVEL] message`
   - Niveaux disponibles : INFO, WARNING, ERROR, DEBUG
   - Envoyer les erreurs sur stderr avec `>&2`

3. **Paramètres**
   - Valider tous les paramètres reçus
   - Fournir des valeurs par défaut si possible
   - Documenter les paramètres requis

4. **Codes de Retour**
   - 0 : Succès
   - 1 : Erreur générale
   - Autres codes pour des erreurs spécifiques

5. **Sécurité**
   - Valider et échapper les entrées utilisateur
   - Utiliser des chemins absolus
   - Gérer les erreurs et les cas limites

## Exemple de Configuration

```yaml
name: Mon Plugin Bash
description: Description de mon plugin
version: 1.0
category: Installation
multiple: false
icon: 🔧
config_fields:
  hostname:
    type: text
    label: Nom d'hôte
    description: Nom d'hôte du serveur
    required: true
    validate: no_spaces
    default: "localhost"
  
  port:
    type: text
    label: Port
    description: Port du service
    required: true
    validate: port
    default: "8080"
  
  ssl:
    type: checkbox
    label: Activer SSL
    description: Activer le support SSL
    default: false
  
  cert_path:
    type: directory
    label: Certificats
    description: Dossier des certificats SSL
    enabled_if:
      field: ssl
      value: true
```
