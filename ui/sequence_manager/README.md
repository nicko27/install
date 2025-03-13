# Gestionnaire de Séquences pcUtils

Ce module gère l'exécution conditionnelle des séquences de plugins pcUtils.

## Structure des Fichiers

```
sequence_manager/
├── sequence_manager.py    # Gestionnaire de séquences
└── README.md             # Documentation
```

## Fonctionnalités

### 1. Exécution Conditionnelle

- Conditions basées sur les résultats des plugins précédents
- Support des variables d'environnement système
- Opérateurs de comparaison flexibles (==, !=, >, <, >=, <=, in, not in)

### 2. Variables d'Exportation

- Format par défaut : `NOM_PLUGIN_STATUS`
- Format personnalisé via `export_result`
- Conservation automatique des résultats

### 3. Gestion des Erreurs

- Option globale `stop_on_first_fail`
- Continuation par défaut si pas de résultat
- Logs détaillés en français

## Format des Séquences

```yaml
name: Nom de la Séquence
description: Description détaillée
stop_on_first_fail: true  # Optionnel

steps:
  - plugin: nom_plugin
    export_result: NOM_VARIABLE  # Optionnel
    conditions:  # Optionnel
      - variable: PLUGIN_PRECEDENT_STATUS
        operator: '=='
        value: true
    config:
      param1: valeur1
      param2: valeur2
```

## Exemple d'Utilisation

```yaml
# Installation d'imprimante avec vérifications
name: Installation Imprimante
description: Installation avec vérifications réseau
stop_on_first_fail: true

steps:
  # Vérification réseau
  - plugin: network_check
    export_result: NETWORK_STATUS
    config:
      check_type: basic
      target_hosts: 
        - printer.local

  # Installation si réseau OK
  - plugin: add_printer
    conditions:
      - variable: NETWORK_STATUS
        operator: '=='
        value: true
    config:
      printer_name: Bureau_01
```

## Variables d'Environnement

Les variables sont automatiquement exportées après chaque étape :

```python
# Exemple de variables disponibles
{
    'NETWORK_CHECK_STATUS': True,    # Nom par défaut
    'NETWORK_STATUS': True,          # Nom personnalisé
    'ADD_PRINTER_STATUS': True       # Nom par défaut
}
```

## Gestion des Erreurs

1. **Validation**
   - Vérification du format YAML
   - Validation des champs requis
   - Contrôle des types de données

2. **Exécution**
   - Vérification des conditions
   - Gestion des erreurs de plugin
   - Logs détaillés pour le débogage

## Journalisation

Tous les messages sont en français :

```python
logger.debug("Séquence chargée : installation_complete")
logger.warning("Variable non trouvée : NETWORK_STATUS")
logger.error("Erreur lors de l'évaluation : valeur=True, attendu=False")
```

## Tests

Les tests unitaires sont disponibles dans :
```
tests/test_sequence_manager.py
```

## Dépendances

- `ruamel.yaml` : Gestion des fichiers YAML
- `logging` : Journalisation en français
- Composants internes pcUtils
