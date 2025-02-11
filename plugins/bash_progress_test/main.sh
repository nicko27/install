#!/bin/bash

# Fichier de log
LOG_FILE="/media/nico/Drive/install/logs/bash_progress_test.log"

# Fonction de log
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

# Fonction principale de test
run_bash_test() {
    local test_name="$1"
    local test_intensity="$2"

    log "DEBUG" "Début de run_bash_test avec test_name='$test_name', test_intensity='$test_intensity'"

    # Validation des paramètres
    if [[ -z "$test_name" || -z "$test_intensity" ]]; then
        log "ERROR" "Nom ou intensité du test manquant"
        return 1
    fi

    log "INFO" " Démarrage du test Bash : $test_name"

    # Configuration basée sur l'intensité
    local total_steps=0
    local max_delay=0
    local complexity_factor=0

    case "$test_intensity" in
        "light")
            total_steps=5
            max_delay=0.5
            complexity_factor=1
            ;;
        "medium")
            total_steps=10
            max_delay=1.0
            complexity_factor=2
            ;;
        "heavy")
            total_steps=20
            max_delay=2.0
            complexity_factor=3
            ;;
        *)
            log "ERROR" "Intensité de test invalide : $test_intensity"
            return 1
            ;;
    esac

    log "DEBUG" "Configuration du test : étapes=$total_steps, délai max=$max_delay, facteur=$complexity_factor"

    # Simulation de progression
    for ((step=1; step<=total_steps; step++)); do
        # Calcul du pourcentage
        local percentage=$((step * 100 / total_steps))
        
        # Log de progression
        log "INFO" "Progression : $percentage% (étape $step/$total_steps)"
        
        # Simulation de travail
        sleep "$max_delay"
        
        # Simulation de calculs complexes
        for ((i=0; i<1000*complexity_factor; i++)); do
            ((i**complexity_factor))
        done
    done

    # Fin du test
    log "INFO" " Test Bash terminé avec succès"
    return 0
}

# Fonction principale
main() {
    log "DEBUG" "Début de l'exécution du script avec arguments : $*"

    # Log détaillé des arguments
    log "DEBUG" "Nombre total d'arguments : $#"
    log "DEBUG" "Arguments complets : $*"
    for i in $(seq 0 $#); do
        log "DEBUG" "Argument $i : '${!i}'"
    done
    log "DEBUG" "Nom du script : $0"
    log "DEBUG" "Répertoire de travail : $(pwd)"

    # Gestion flexible des arguments
    if [[ $# -eq 1 ]]; then
        # Un seul argument : considéré comme le nom du test
        run_bash_test "$1" "light"
        exit_code=$?
    elif [[ $# -eq 2 ]]; then
        # Deux arguments : nom du test et intensité
        run_bash_test "$1" "$2"
        exit_code=$?
    else
        log "ERROR" "Utilisation incorrecte : $0 <test_name> [test_intensity]"
        exit 1
    fi

    if [[ $exit_code -eq 0 ]]; then
        log "INFO" " Test Bash $1 réussi"
        exit 0
    else
        log "ERROR" " Test Bash $1 échoué"
        exit 1
    fi
}

# Exécuter le script avec les arguments fournis
main "$@"
