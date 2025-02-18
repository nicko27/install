import os
import sys
import pexpect
import asyncio
from typing import Dict, Any

async def run(config: Dict[str, Any], progress_callback=None) -> bool:
    """Exécute le script interactif et fournit les réponses automatiquement.
    
    Args:
        config: Configuration du plugin avec script_path et responses
        progress_callback: Callback pour mettre à jour la progression
        
    Returns:
        bool: True si succès, False sinon
    """
    try:
        script_path = config.get('script_path')
        responses = config.get('responses', [])
        
        if not script_path or not os.path.exists(script_path):
            raise ValueError(f"Script introuvable: {script_path}")
            
        if not responses:
            raise ValueError("Aucune réponse fournie pour le script interactif")
            
        # Lancer le script
        if progress_callback:
            await progress_callback(0.1, "Démarrage du script...")
            
        # Utiliser pexpect pour interagir avec le script
        child = pexpect.spawn(f'bash {script_path}')
        
        # Pour chaque réponse attendue
        for i, response in enumerate(responses, 1):
            # Attendre que le script demande une entrée (le prompt read)
            child.expect('.*\n')  # Attend une nouvelle ligne
            
            # Envoyer la réponse
            child.sendline(response)
            
            if progress_callback:
                progress = (i / len(responses)) * 0.9 + 0.1
                await progress_callback(progress, f"Réponse {i}/{len(responses)} envoyée")
                
        # Attendre la fin du script
        child.expect(pexpect.EOF)
        
        if progress_callback:
            await progress_callback(1.0, "Script terminé")
            
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
