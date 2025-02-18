#!/bin/bash

# Fonction pour afficher une étape
show_step() {
    echo "\n=== Étape: $1 ==="
}

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

show_step "Initialisation de la configuration"
echo "Détection du système..."
sleep 1
echo "Vérification des prérequis..."
sleep 1

show_step "Type d'installation"
echo "Voulez-vous installer un serveur web ? (o/n)"
web_server=$(validate_yes_no)

if [ "$web_server" = "oui" ]; then
    show_step "Configuration du serveur web"
    echo "Quel port souhaitez-vous utiliser ? (par défaut: 80)"
    read port
    if [ -z "$port" ]; then
        port=80
        echo "Utilisation du port par défaut: $port"
    else
        echo "Port sélectionné: $port"
    fi
    
    show_step "Support PHP"
    echo "Voulez-vous activer PHP ? (o/n)"
    php_support=$(validate_yes_no)
    
    if [ "$php_support" = "oui" ]; then
        show_step "Version de PHP"
        echo "Quelle version de PHP ? (7.4/8.0/8.1)"
        read php_version
        case $php_version in
            "7.4"|"8.0"|"8.1" )
                echo "PHP $php_version sera installé"
                sleep 1;;
            * )
                echo "Version non supportée, utilisation de 8.1 par défaut"
                php_version="8.1"
                sleep 1;;
        esac
    fi
else
    show_step "Configuration de la base de données"
    echo "Quel type de base de données souhaitez-vous installer ?"
    echo "Options disponibles : mysql, postgresql"
    read db_type
    
    case $db_type in
        "mysql"|"postgresql" )
            echo "Configuration de $db_type..."
            sleep 1
            
            show_step "Port de la base de données"
            echo "Port pour $db_type ? (mysql=3306, postgresql=5432)"
            read db_port
            if [ -z "$db_port" ]; then
                if [ "$db_type" = "mysql" ]; then
                    db_port=3306
                else
                    db_port=5432
                fi
                echo "Utilisation du port par défaut: $db_port"
            else
                echo "Port sélectionné: $db_port"
            fi
            
            show_step "Sécurité"
            echo "Veuillez entrer le mot de passe root pour $db_type :"
            read -s db_password
            echo "Mot de passe enregistré"
            echo
            sleep 1;;
        * )
            echo "Type de base de données non supporté"
            echo "Configuration annulée"
            exit 1;;
    esac
fi

show_step "Résumé de la configuration"
echo "Vérification des paramètres..."
sleep 1

if [ "$web_server" = "oui" ]; then
    echo "Configuration serveur web :"
    echo "- Port: $port"
    if [ "$php_support" = "oui" ]; then
        echo "- PHP: version $php_version"
    else
        echo "- PHP: désactivé"
    fi
else
    echo "Configuration base de données :"
    echo "- Type: $db_type"
    echo "- Port: $db_port"
    echo "- Mot de passe root: configuré"
fi

echo
show_step "Validation"
echo "Confirmer la configuration ? (o/n)"
confirm=$(validate_yes_no)

if [ "$confirm" = "oui" ]; then
    show_step "Finalisation"
    echo "Configuration validée !"
    echo "Le système est prêt pour l'installation"
    exit 0
else
    show_step "Annulation"
    echo "Configuration annulée."
    echo "Aucune modification n'a été effectuée"
    exit 1
fi
