#!/bin/bash
# Traiter les paramètres
EXTRACT_DIR="."
DEBUG=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --extract_dir=*)
            EXTRACT_DIR="${1#*=}"
            ;;
        --debug)
            DEBUG=1
            ;;
    esac
    shift
done

if [ -z "$EXTRACT_DIR" ]; then
    echo "Error: --extract_dir parameter is required"
    exit 1
fi

# Créer le dossier logs s'il n'existe pas
mkdir -p "$EXTRACT_DIR/logs"


# Lancer l'application
if [ "$DEBUG" -eq 1 ]; then
    textual run "$EXTRACT_DIR/main.py" --dev
else
    python3 "$EXTRACT_DIR/main.py"
fi
