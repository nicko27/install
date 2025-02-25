# Script Interactive Plugin

Ce plugin permet d'exécuter des scripts shell interactifs en automatisant les réponses aux questions.

## Configuration

### Type d'installation

- **Installer un serveur web** : Si activé, configure un serveur web avec support PHP optionnel. Sinon, configure une base de données.

### Configuration serveur web

Si vous choisissez d'installer un serveur web :
- **Port** : Port d'écoute du serveur web (1-65535)
- **Support PHP** : Activer/désactiver le support PHP
- **Version PHP** : Version de PHP à installer (7.4/8.0/8.1)

### Configuration base de données

Si vous choisissez d'installer une base de données :
- **Type** : MySQL ou PostgreSQL
- **Port** : Port d'écoute (par défaut : 3306 pour MySQL, 5432 pour PostgreSQL)
- **Mot de passe root** : Mot de passe administrateur (minimum 6 caractères)

## Presets

Le plugin inclut trois configurations prédéfinies :

1. **Serveur Web avec PHP**
   - Serveur web sur le port 80
   - PHP 8.1 activé

2. **Serveur MySQL**
   - MySQL sur le port 3306
   - Mot de passe root par défaut

3. **Serveur PostgreSQL**
   - PostgreSQL sur le port 5432
   - Mot de passe root par défaut

## Utilisation

### Interface graphique

1. Sélectionnez le plugin dans l'interface
2. Configurez les options selon vos besoins
3. Cliquez sur "Démarrer"

### Ligne de commande

```bash
# Configuration serveur web par défaut
python3 main.py --plugin script_interactive_1

# Configuration MySQL
python3 main.py --plugin script_interactive_1 --params "install_web_server=false"

# Configuration personnalisée
python3 main.py --plugin script_interactive_1 --params "web_server_port=8080" "php_version=8.0"
```

## Structure des fichiers

- `exec.py` : Logique d'exécution du plugin
- `settings.yml` : Configuration du plugin et valeurs par défaut
- `presets.yml` : Configurations prédéfinies
- `test_script.sh` : Script de test interactif
