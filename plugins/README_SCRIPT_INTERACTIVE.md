# Guide de création d'un plugin script_interactif

Ce guide explique comment créer un plugin qui exécute un script shell interactif en automatisant les réponses aux questions.

## Structure du plugin

```
mon_plugin/
├── __init__.py     # Point d'entrée Python
├── exec.py         # Logique d'exécution
├── settings.yml    # Configuration du plugin
└── script.sh       # Script shell interactif
```

## 1. Configuration (settings.yml)

Le fichier `settings.yml` définit l'interface et les paramètres du plugin :

```yaml
name: Mon Plugin
description: Description de ce que fait le plugin
version: 1.0
category: Installation
multiple: false     # true si plusieurs instances peuvent être exécutées
icon: 🔧           # Icône affichée dans l'interface

config_fields:
  # Exemple de champ texte
  hostname:
    type: text
    label: Nom d'hôte
    description: Nom d'hôte du serveur
    default: "localhost"
    required: true
    validate: no_spaces
    min_length: 3
    not_empty: true
    
  # Exemple de champ nombre
  port:
    type: text
    label: Port
    description: Port d'écoute (1-65535)
    default: "80"
    validate: number
    min: 1
    max: 65535
    required: true
    
  # Exemple de case à cocher
  ssl:
    type: checkbox
    label: Activer SSL
    description: Activer le support SSL/TLS
    default: true
    
  # Exemple de liste déroulante
  php_version:
    type: select
    label: Version PHP
    description: Version de PHP à installer
    options:
      - "7.4"
      - "8.0"
      - "8.1"
    default: "8.1"
    condition: ssl  # N'apparaît que si ssl est coché
    
  # Exemple de champ dépendant
  db_port:
    type: text
    label: Port base de données
    description: Port d'écoute de la base de données
    validate: number
    min: 1
    max: 65535
    required: true
    default: "3306"
    depends_on: db_type    # Dépend du champ db_type
    values:                # Valeurs selon db_type
      mysql: "3306"
      postgresql: "5432"
```

### Types de champs disponibles

1. **text** : Champ texte
   - `validate`: Type de validation (number, no_spaces)
   - `min_length`: Longueur minimale
   - `max_length`: Longueur maximale
   - `not_empty`: Doit contenir une valeur
   - `placeholder`: Texte d'exemple

2. **checkbox** : Case à cocher
   - `default`: true/false

3. **select** : Liste déroulante
   - `options`: Liste des options
   - `default`: Valeur par défaut
   - `allow_blank`: Autoriser une valeur vide

4. **password** : Champ mot de passe
   - Mêmes options que text
   - Masque la valeur

### Validation et dépendances

1. **Validation**
   - `required`: Champ obligatoire
   - `validate`: Type de validation
   - `min`/`max`: Valeurs min/max pour les nombres
   - `min_length`/`max_length`: Longueur min/max pour le texte

2. **Dépendances**
   - `condition`: Le champ n'apparaît que si la condition est vraie
   - `depends_on`: La valeur dépend d'un autre champ
   - `values`: Valeurs selon le champ dont on dépend

## 2. Script Shell (script.sh)

Le script shell qui pose les questions et traite les réponses :

```bash
#!/bin/bash

# Fonction pour afficher la progression
progress() {
    echo "[PROGRESS] $1 : $2%"
}

# Question 1 : Nom d'hôte
echo "Quel est le nom d'hôte ? "
read hostname
progress "Configuration nom d'hôte" 20

# Question 2 : Port
echo "Quel port utiliser ? "
read port
progress "Configuration port" 40

# Question 3 : SSL
echo "Activer SSL ? (o/n) "
read ssl
progress "Configuration SSL" 60

if [ "$ssl" = "o" ]; then
    # Question 4 : Version PHP (si SSL activé)
    echo "Quelle version de PHP ? "
    read php_version
    progress "Configuration PHP" 80
fi

# Question finale
echo "Confirmer la configuration ? (o/n) "
read confirm
progress "Finalisation" 100

if [ "$confirm" = "o" ]; then
    echo "Configuration terminée avec succès"
    exit 0
else
    echo "Configuration annulée"
    exit 1
fi
```

### Règles pour le script

1. Utiliser `read` pour les questions
2. Afficher la progression avec `[PROGRESS] Message : Pourcentage%`
3. Retourner 0 en cas de succès, autre chose en cas d'erreur
4. Gérer proprement les erreurs et les cas particuliers

## 3. Fichier Python (exec.py)

Le fichier qui gère l'exécution du script :

```python
#!/usr/bin/env python3
import os
import sys
import json
import time
import pexpect
import logging
from datetime import datetime

# Configuration du logging
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_FILE = os.path.join(BASE_DIR, "logs", "mon_plugin.log")
formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

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

def print_progress(step: int, total: int, message: str = None):
    """Affiche la progression"""
    progress = int((step * 100) / total)
    msg = f"Progression : {progress}% (étape {step}/{total})"
    if message:
        msg += f" - {message}"
    logger.info(msg)
    sys.stdout.flush()

def config_to_responses(config):
    """Convertit la configuration en liste de réponses."""
    responses = []
    
    # Exemple : convertir la config en réponses
    responses.append(config.get('hostname', 'localhost'))
    responses.append(str(config.get('port', 80)))
    responses.append('o' if config.get('ssl', True) else 'n')
    
    if config.get('ssl', True):
        responses.append(config.get('php_version', '8.1'))
    
    # Toujours ajouter la confirmation finale
    responses.append('o')
    
    return responses

def execute_plugin(config):
    """Point d'entrée pour l'exécution du plugin."""
    try:
        logger.info("Démarrage de l'exécution du script interactif")
        
        # Chemin du script dans le dossier du plugin
        script_path = os.path.join(os.path.dirname(__file__), 'script.sh')
        if not os.path.exists(script_path):
            raise ValueError(f"Script introuvable: {script_path}")
        
        # Convertir la configuration en réponses
        responses = config_to_responses(config)
        total_steps = len(responses) * 2  # Questions + Réponses
        current_step = 0
        
        # Utiliser pexpect avec un buffer plus grand
        child = pexpect.spawn(f'bash {script_path}', encoding='utf-8')
        
        # Pour chaque réponse attendue
        for i, response in enumerate(responses, 1):
            # Attendre une sortie
            current_step += 1
            print_progress(current_step, total_steps, "Attente de la question...")
            
            index = child.expect(['.*\\n', pexpect.EOF, pexpect.TIMEOUT])
            if index != 0:
                raise RuntimeError("Le script s'est terminé ou ne répond pas")
            
            # Récupérer la sortie
            output = child.before + child.after
            logger.info(f"Question : {output.strip()}")
            
            # Envoyer la réponse
            current_step += 1
            # Masquer le mot de passe dans les logs
            displayed_response = '****' if 'mot de passe' in output.lower() else response
            print_progress(current_step, total_steps, f"Réponse : {displayed_response}")
            
            child.sendline(response)
            time.sleep(0.5)  # Petite pause pour la lisibilité
        
        # Attendre la fin du script
        child.expect(pexpect.EOF)
        
        # Vérifier le code de retour
        child.close()
        if child.exitstatus == 0:
            logger.info("Exécution terminée avec succès")
            return True
        else:
            raise RuntimeError(f"Le script a retourné le code {child.exitstatus}")
            
    except Exception as e:
        error_msg = f"Erreur lors de l'exécution : {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: exec.py <config_json>")
        sys.exit(1)
        
    try:
        config = json.loads(sys.argv[1])
        execute_plugin(config)
    except Exception as e:
        logger.error(f"Erreur : {str(e)}")
        sys.exit(1)
```

## Utilisation

1. Créer un nouveau dossier dans `plugins/`
2. Copier les fichiers de base
3. Adapter `settings.yml` selon vos besoins
4. Créer votre script shell
5. Adapter `exec.py` pour convertir la configuration en réponses

## Bonnes pratiques

1. **Validation**
   - Valider toutes les entrées utilisateur
   - Définir des valeurs par défaut sensées
   - Utiliser des conditions pour masquer les champs non pertinents

2. **Interface**
   - Grouper les champs logiquement
   - Donner des descriptions claires
   - Utiliser des placeholders pour les exemples

3. **Script**
   - Gérer tous les cas d'erreur
   - Afficher la progression
   - Valider les réponses reçues

4. **Logging**
   - Logger toutes les actions importantes
   - Masquer les informations sensibles
   - Inclure les erreurs détaillées

## Exemple complet

Voir le plugin `script_interactive` pour un exemple complet d'implémentation.
