# Templates de Configuration

Ce dossier contient les templates de configuration pour tous les plugins pcUtils.

## Structure

```
templates/
├── add_printer/           # Templates pour l'ajout d'imprimantes
│   ├── default.yml       # Configuration par défaut
│   ├── imprimante_bureau.yml
│   └── imprimante_etage.yml
├── scan_plugin/          # Templates pour la numérisation
│   ├── default.yml       # Configuration par défaut
│   └── utilisateur_standard.yml
└── template_schema.yml   # Schéma de validation des templates
```

## Format des Templates

Chaque template est un fichier YAML avec la structure suivante :

```yaml
name: Nom du Template
description: Description détaillée
variables:
  variable1: valeur1
  variable2: valeur2
```

## Templates Disponibles

### Plugin add_printer

1. **default.yml** - Configuration par défaut
   ```yaml
   printer_name: Bureau_RDC
   printer_model: KM227
   printer_ip: 192.168.1.100
   ```

2. **imprimante_bureau.yml** - Configuration bureau
   ```yaml
   printer_name: Bureau_Principal
   printer_model: KM227C
   printer_ip: 192.168.1.101
   ```

3. **imprimante_etage.yml** - Configuration étage
   ```yaml
   printer_name: Etage_1
   printer_model: KM301iC
   printer_ip: 192.168.1.200
   ```

### Plugin scan_plugin

1. **default.yml** - Configuration par défaut
   ```yaml
   user: scan
   password: scan_secure_2024
   scan_directory: /partage/commun/Numerisation
   ```

2. **utilisateur_standard.yml** - Configuration utilisateur
   ```yaml
   user: scan
   password: scan_2024
   scan_directory: /partage/utilisateurs/scan
   ```

## Utilisation

1. Le template `default.yml` est automatiquement chargé s'il existe
2. Les autres templates peuvent être sélectionnés dans l'interface
3. Les valeurs peuvent être modifiées après l'application d'un template

## Ajout de Nouveaux Templates

1. Créez un fichier `.yml` dans le dossier du plugin concerné
2. Suivez le format défini dans `template_schema.yml`
3. Utilisez des noms descriptifs en minuscules avec underscores
4. Incluez une description claire de l'utilisation prévue
