import os
import sys
import pexpect
import asyncio
import re
from typing import Dict, Any, Optional, Tuple, List

def extract_question(output: str) -> Optional[str]:
    """Extrait la question du texte de sortie."""
    # Cherche une ligne se terminant par ? ou contenant 'read'
    lines = output.split('\n')
    for line in reversed(lines):
        if line.strip().endswith('?') or 'read' in line.lower():
            return line.strip()
    return None

def config_to_responses(config: Dict[str, Any]) -> List[str]:
    """Convertit la configuration en liste de réponses pour le script."""
    responses = []
    
    # Réponse pour le serveur web
    install_web = config.get('install_web_server', True)
    responses.append('o' if install_web else 'n')
    
    if install_web:
        # Port du serveur web
        port = str(config.get('web_server_port', 80))
        responses.append(port)
        
        # Support PHP
        enable_php = config.get('enable_php', True)
        responses.append('o' if enable_php else 'n')
        
        if enable_php:
            # Version PHP
            php_version = config.get('php_version', '8.1')
            responses.append(php_version)
    else:
        # Type de base de données
        db_type = config.get('db_type', 'mysql')
        responses.append(db_type)
        
        # Port de la base de données
        db_port = str(config.get('db_port', 3306 if db_type == 'mysql' else 5432))
        responses.append(db_port)
        
        # Mot de passe root
        db_password = config.get('db_root_password', '')
        responses.append(db_password)
    
    # Confirmation finale
    confirm = config.get('confirm_config', True)
    responses.append('o' if confirm else 'n')
    
    return responses

async def run(config: Dict[str, Any], progress_callback=None) -> bool:
    """Exécute le script interactif et fournit les réponses automatiquement.
    
    Args:
        config: Configuration du plugin
        progress_callback: Callback pour mettre à jour la progression
        
    Returns:
        bool: True si succès, False sinon
    """
    try:
        # Chemin du script dans le dossier du plugin
        script_path = os.path.join(os.path.dirname(__file__), 'test_script.sh')
        if not os.path.exists(script_path):
            raise ValueError(f"Script introuvable: {script_path}")
        
        # Convertir la configuration en réponses
        responses = config_to_responses(config)
        
        # Initialisation de la progression
        total_steps = len(responses) * 2 + 2  # Questions + Réponses + Début + Fin
        current_step = 0
        
        def update_progress(step_name: str) -> None:
            if progress_callback:
                progress = current_step / total_steps
                asyncio.create_task(progress_callback(progress, step_name))
        
        # Démarrage
        current_step += 1
        update_progress("Démarrage du script...")
        
        # Utiliser pexpect avec un buffer plus grand
        child = pexpect.spawn(f'bash {script_path}', encoding='utf-8')
        child.logfile = sys.stdout  # Pour le débogage si nécessaire
        
        # Pour chaque réponse attendue
        for i, response in enumerate(responses, 1):
            # Attendre une sortie et capturer la question
            index = child.expect(['.*\n', pexpect.EOF, pexpect.TIMEOUT])
            if index != 0:
                raise RuntimeError("Le script s'est terminé ou ne répond pas")
                
            # Récupérer la sortie et chercher la question
            output = child.before + child.after
            question = extract_question(output)
            
            # Mettre à jour la progression - Question reçue
            current_step += 1
            if question:
                update_progress(f"Question {i}: {question}")
            else:
                update_progress(f"Attente de la question {i}...")
            
            # Envoyer la réponse
            child.sendline(response)
            
            # Mettre à jour la progression - Réponse envoyée
            current_step += 1
            # Masquer le mot de passe dans les logs
            displayed_response = '****' if 'mot de passe' in question.lower() if question else response
            update_progress(f"Réponse {i}: {displayed_response}")
            
            # Petite pause pour laisser le temps de lire
            await asyncio.sleep(0.5)
        
        # Attendre la fin du script
        child.expect(pexpect.EOF)
        
        # Finalisation
        current_step += 1
        update_progress("Configuration terminée")
        
        # Vérifier le code de retour
        child.close()
        if child.exitstatus == 0:
            return True
        else:
            raise RuntimeError(f"Le script a retourné le code {child.exitstatus}")
            
    except pexpect.TIMEOUT:
        raise RuntimeError("Le script n'a pas répondu dans le temps imparti")
    except pexpect.EOF:
        raise RuntimeError("Le script s'est terminé de manière inattendue")
    except Exception as e:
        raise RuntimeError(f"Erreur lors de l'exécution du script: {str(e)}")
