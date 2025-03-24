#!/bin/bash

# Dossier où se trouvent les fichiers .whl
WHL_DIR="./libs"

# Créer le dossier libs s'il n'existe pas
mkdir -p libs

# Parcourir tous les fichiers .whl dans le dossier spécifié
for whl in "$WHL_DIR"/*.whl; do
    # Vérifier que le fichier existe
    if [ -f "$whl" ]; then
        # Extraire le nom du paquet (sans l'extension)
        pakname=$(basename "$whl" .whl)
        
        # Créer un sous-dossier pour chaque paquet
        mkdir -p "libs/$pakname"
        
        # Dézipper le fichier .whl dans son dossier
        unzip -q "$whl" -d "libs/$pakname"
        
        echo "Extrait: $whl vers libs/$pakname"
    fi
done

echo "Tous les fichiers .whl ont été extraits dans le dossier libs/"
