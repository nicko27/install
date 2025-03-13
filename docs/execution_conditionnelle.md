# Guide d'Exécution Conditionnelle pcUtils

Ce guide explique comment utiliser l'exécution conditionnelle dans les séquences pcUtils.

## Table des Matières

1. [Concepts de Base](#concepts-de-base)
2. [Variables d'Exportation](#variables-dexportation)
3. [Conditions d'Exécution](#conditions-dexécution)
4. [Gestion des Erreurs](#gestion-des-erreurs)
5. [Exemples Pratiques](#exemples-pratiques)

## Concepts de Base

### Séquence d'Exécution

Une séquence définit une série d'étapes à exécuter dans un ordre précis :

```yaml
name: Ma Séquence
description: Description détaillée
stop_on_first_fail: true  # Optionnel

steps:
  - plugin: mon_plugin
    # ... configuration ...
```

### Variables d'Environnement

Chaque plugin peut exporter son résultat dans l'environnement :

- **Nom par défaut** : `NOM_PLUGIN_STATUS`
- **Nom personnalisé** : Via `export_result`

## Variables d'Exportation

### Format Standard

```yaml
steps:
  - plugin: network_check
    # Utilise NETWORK_CHECK_STATUS par défaut
```

### Format Personnalisé

```yaml
steps:
  - plugin: network_check
    export_result: NETWORK_STATUS
    # Utilise NETWORK_STATUS
```

### Bonnes Pratiques

1. **Nommage Explicite**
   ```yaml
   export_result: PRINTER_NETWORK_STATUS
   # Plus clair que NETWORK_STATUS
   ```

2. **Convention de Nommage**
   ```yaml
   # Recommandé
   export_result: NETWORK_AVAILABLE
   
   # À éviter
   export_result: networkStatus
   ```

## Conditions d'Exécution

### Opérateurs Disponibles

| Opérateur | Description | Exemple |
|-----------|-------------|---------|
| `==` | Égalité | `value: true` |
| `!=` | Différence | `value: false` |
| `>` | Supérieur | `value: 100` |
| `<` | Inférieur | `value: 50` |
| `>=` | Supérieur ou égal | `value: 0` |
| `<=` | Inférieur ou égal | `value: 1000` |
| `in` | Contenu dans | `value: [1, 2, 3]` |
| `not in` | Non contenu dans | `value: ["error", "failed"]` |

### Exemples de Conditions

```yaml
conditions:
  # Vérification simple
  - variable: NETWORK_STATUS
    operator: '=='
    value: true

  # Vérification numérique
  - variable: DISK_SPACE
    operator: '>='
    value: 500

  # Vérification de liste
  - variable: ERRORS
    operator: 'in'
    value: ["timeout", "connection_failed"]
```

## Gestion des Erreurs

### Option stop_on_first_fail

```yaml
# Niveau global
stop_on_first_fail: true

steps:
  - plugin: critical_step
    # Arrêt si échec
```

### Continuation par Défaut

Si `export_result` n'est pas spécifié ou si la variable n'existe pas :
- La séquence continue
- Un message de log est généré

### Messages de Log

```python
# Exemples de messages
"Variable d'environnement non trouvée : NETWORK_STATUS"
"Condition non satisfaite : valeur actuelle = False, attendue == True"
"Types incompatibles : valeur=<str>, attendu=<int>"
```

## Exemples Pratiques

### Installation d'Imprimante

```yaml
name: Installation Imprimante
steps:
  # 1. Vérification réseau
  - plugin: network_check
    export_result: NETWORK_STATUS
    config:
      timeout: 5

  # 2. Installation si réseau OK
  - plugin: add_printer
    conditions:
      - variable: NETWORK_STATUS
        operator: '=='
        value: true
    config:
      printer_name: Bureau01

  # 3. Test si installation OK
  - plugin: print_test
    conditions:
      - variable: ADD_PRINTER_STATUS
        operator: '=='
        value: true
```

### Vérification Système

```yaml
steps:
  # 1. Vérification espace disque
  - plugin: disk_check
    export_result: DISK_SPACE
    config:
      min_space: 500

  # 2. Vérification mémoire
  - plugin: memory_check
    conditions:
      - variable: DISK_SPACE
        operator: '>='
        value: 500
    export_result: MEMORY_STATUS

  # 3. Installation si tout OK
  - plugin: install_software
    conditions:
      - variable: DISK_SPACE
        operator: '>='
        value: 500
      - variable: MEMORY_STATUS
        operator: '=='
        value: true
```

### Gestion des Erreurs Avancée

```yaml
name: Installation Sécurisée
stop_on_first_fail: true

steps:
  # 1. Vérifications préalables
  - plugin: security_check
    export_result: SECURITY_STATUS
    config:
      check_permissions: true

  # 2. Sauvegarde
  - plugin: backup
    conditions:
      - variable: SECURITY_STATUS
        operator: '=='
        value: true
    export_result: BACKUP_STATUS

  # 3. Installation
  - plugin: install
    conditions:
      - variable: BACKUP_STATUS
        operator: '=='
        value: true
      - variable: SECURITY_STATUS
        operator: '=='
        value: true
```

## Conseils et Astuces

1. **Nommage Explicite**
   ```yaml
   # Bon
   export_result: PRINTER_NETWORK_STATUS
   
   # Moins bon
   export_result: STATUS
   ```

2. **Conditions Groupées**
   ```yaml
   conditions:
     - variable: SYSTEM_CHECK
       operator: '=='
       value: true
     - variable: NETWORK_CHECK
       operator: '=='
       value: true
   ```

3. **Validation des Types**
   ```yaml
   # Vérifier le type avant comparaison
   conditions:
     - variable: COUNT
       operator: '>'
       value: 0  # Assurez-vous que COUNT est un nombre
   ```

4. **Documentation des Variables**
   ```yaml
   # En-tête de séquence
   name: Ma Séquence
   description: |
     Variables exportées :
     - NETWORK_STATUS : État du réseau (bool)
     - DISK_SPACE : Espace disque en MB (int)
   ```
