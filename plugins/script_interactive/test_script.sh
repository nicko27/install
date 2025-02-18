#!/bin/bash

# Fonction pour valider oui/non
validate_yes_no() {
    while true; do
        read reponse
        case $reponse in
            [OoYy]* ) echo "oui"; return;;
            [Nn]* ) echo "non"; return;;
            * ) echo "Répondez par oui (o/O/y/Y) ou non (n/N)" >&2;;
        esac
    done
}

echo "=== Configuration du serveur ==="
echo
echo "Voulez-vous installer un serveur web ? (o/n)"
web_server=$(validate_yes_no)

if [ "$web_server" = "oui" ]; then
    echo "Quel port souhaitez-vous utiliser ? (par défaut: 80)"
    read port
    if [ -z "$port" ]; then
        port=80
    fi
    echo "Configuration du serveur web sur le port $port"
    
    echo "Voulez-vous activer PHP ? (o/n)"
    php_support=$(validate_yes_no)
    
    if [ "$php_support" = "oui" ]; then
        echo "Quelle version de PHP ? (7.4/8.0/8.1)"
        read php_version
        case $php_version in
            "7.4"|"8.0"|"8.1" )
                echo "PHP $php_version sera installé";;
            * )
                echo "Version non supportée, utilisation de 8.1 par défaut"
                php_version="8.1";;
        esac
    fi
else
    echo "Installation d'un serveur de base de données uniquement"
    echo "Quel type de base de données ? (mysql/postgresql)"
    read db_type
    
    case $db_type in
        "mysql"|"postgresql" )
            echo "Port pour $db_type ? (mysql=3306, postgresql=5432)"
            read db_port
            if [ -z "$db_port" ]; then
                if [ "$db_type" = "mysql" ]; then
                    db_port=3306
                else
                    db_port=5432
                fi
            fi
            echo "Mot de passe root ?"
            read -s db_password
            echo
            echo "Configuration de $db_type sur le port $db_port";;
        * )
            echo "Type non supporté, configuration annulée"
            exit 1;;
    esac
fi

echo
echo "=== Résumé de la configuration ==="
if [ "$web_server" = "oui" ]; then
    echo "- Serveur web sur le port $port"
    if [ "$php_support" = "oui" ]; then
        echo "- Support PHP $php_version"
    else
        echo "- Sans support PHP"
    fi
else
    echo "- Base de données $db_type"
    echo "- Port $db_port"
fi

echo
echo "Confirmer la configuration ? (o/n)"
confirm=$(validate_yes_no)

if [ "$confirm" = "oui" ]; then
    echo "Configuration validée !"
    exit 0
else
    echo "Configuration annulée."
    exit 1
fi
