#!/usr/bin/env python3
import os
import subprocess
import logging
from get_printer_models import parse_model_file

logger = logging.getLogger(__name__)

def run_command(cmd):
    """Exécute une commande shell et retourne le résultat"""
    try:
        result = subprocess.run(cmd, shell=True, check=True, 
                              capture_output=True, text=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Erreur lors de l'exécution de la commande: {e}")
        return False, e.stderr

class PrinterManager:
    def __init__(self, config):
        self.config = config
        self.models_dir = "/media/nico/Drive/install.sh.extract/imprimantes/modeles"
        
    def get_printer_config(self):
        """Charge la configuration du modèle d'imprimante"""
        model_file = os.path.join(self.models_dir, self.config['printer_model'])
        if not os.path.exists(model_file):
            raise ValueError(f"Modèle d'imprimante non trouvé: {self.config['printer_model']}")
        return parse_model_file(model_file)
        
    def build_printer_options(self, printer_config):
        """Construit les options de l'imprimante"""
        options = []
        
        # Options de base
        if printer_config.get('rectoverso') == '1':
            options.append(printer_config['orectoverso'])
        else:
            options.append(printer_config['orecto'])
            
        # Options couleur
        if printer_config.get('couleurs') == '1':
            options.append(printer_config['ocouleurs'])
        else:
            options.append(printer_config['onb'])
            
        # Format papier
        if printer_config.get('a3') == '1':
            options.append(printer_config['oa3'])
        else:
            options.append(printer_config['oa4'])
            
        # Options communes
        if printer_config.get('ocommun'):
            options.append(printer_config['ocommun'])
            
        return ' '.join(options)
        
    def add_local_printer(self):
        """Ajoute une imprimante locale"""
        try:
            printer_config = self.get_printer_config()
            
            # Construction de la commande
            cmd = f"lpadmin -p {self.config['printer_name']} "
            cmd += f"-v socket://{self.config['printer_ip']} "
            
            # Fichier PPD
            ppd_file = printer_config.get('ppdFile', '').replace('/usr/share/ppd/Gendarmerie-SOLIMP4', '/usr/share/ppd')
            if ppd_file:
                cmd += f"-P {ppd_file} "
                
            # Options de l'imprimante
            options = self.build_printer_options(printer_config)
            if options:
                cmd += f"-o {options} "
                
            cmd += "-E"
            success, output = run_command(cmd)
            
            if success:
                return True, f"Imprimante {self.config['printer_name']} ajoutée avec succès"
            else:
                return False, f"Erreur lors de l'ajout de l'imprimante: {output}"
                
        except Exception as e:
            return False, f"Erreur: {str(e)}"
