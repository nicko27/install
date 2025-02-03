#!/usr/bin/env python3

import os
import argparse
from pathlib import Path

def create_file(directory: str, filename: str = None):
    """
    Crée un fichier dans le répertoire spécifié.
    Si le nom du fichier n'est pas spécifié, il sera demandé plus tard.
    """
    directory_path = Path(directory)
    
    # Crée le répertoire s'il n'existe pas
    if not directory_path.exists():
        directory_path.mkdir(parents=True)
        print(f"Répertoire créé : {directory_path}")
    
    # Si le nom du fichier n'est pas spécifié, on le stocke pour plus tard
    if not filename:
        print("Le nom du fichier sera demandé lors de la configuration")
        return
    
    # Crée le fichier
    file_path = directory_path / filename
    file_path.touch()
    print(f"Fichier créé : {file_path}")

def main():
    parser = argparse.ArgumentParser(description="Créer un fichier dans un répertoire spécifié")
    parser.add_argument("--directory", "-d", required=True, help="Répertoire où créer le fichier")
    parser.add_argument("--filename", "-f", help="Nom du fichier à créer (optionnel)")
    
    args = parser.parse_args()
    create_file(args.directory, args.filename)

if __name__ == "__main__":
    main()
