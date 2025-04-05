"""
Gestionnaire de séquences pour l'écran de sélection.
Gère le chargement et la validation des séquences.
"""

from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from ruamel.yaml import YAML
from logging import getLogger

logger = getLogger('sequence_handler')
yaml = YAML()

class SequenceHandler:
    """
    Gestionnaire de séquences pour l'écran de sélection.
    
    Cette classe est responsable de:
    - Charger les fichiers de séquence YAML
    - Valider la structure des séquences
    - Fournir les séquences disponibles
    """

    def __init__(self):
        """Initialise le gestionnaire de séquences"""
        self.sequences_dir = Path('sequences')
        self.sequence_cache = {}  # Cache pour les séquences chargées
        logger.debug(f"Initialisation du gestionnaire de séquences: {self.sequences_dir}")

    def load_sequence(self, sequence_path: str) -> Optional[Dict[str, Any]]:
        """
        Charge une séquence depuis un fichier YAML avec cache.
        
        Args:
            sequence_path: Chemin vers le fichier de séquence
            
        Returns:
            Données de la séquence ou None en cas d'erreur
        """
        # Vérifier d'abord dans le cache
        if sequence_path in self.sequence_cache:
            logger.debug(f"Séquence trouvée dans le cache: {sequence_path}")
            return self.sequence_cache[sequence_path]
        
        try:
            sequence_file = Path(sequence_path)
            if not sequence_file.exists():
                logger.error(f"Fichier de séquence non trouvé: {sequence_path}")
                return None

            with open(sequence_file, 'r', encoding='utf-8') as f:
                sequence = yaml.load(f)

            validation_result, error_message = self.validate_sequence(sequence)
            if not validation_result:
                logger.error(f"Séquence invalide ({sequence_path}): {error_message}")
                return None

            # Ajouter au cache
            self.sequence_cache[sequence_path] = sequence
            logger.info(f"Séquence chargée et mise en cache: {sequence.get('name', 'Sans nom')}")
            return sequence

        except Exception as e:
            logger.error(f"Erreur lors du chargement de la séquence {sequence_path}: {e}")
            return None

    def validate_sequence(self, sequence: dict) -> Tuple[bool, str]:
        """
        Valide le format d'une séquence.
        
        Args:
            sequence: Données de la séquence à valider
            
        Returns:
            Tuple (validité, message d'erreur)
        """
        if not isinstance(sequence, dict):
            return False, "La séquence doit être un dictionnaire"

        # Vérifier les champs requis
        required_fields = ['name', 'description', 'plugins']
        for field in required_fields:
            if field not in sequence:
                return False, f"Champ requis manquant: {field}"

        if not isinstance(sequence['plugins'], list):
            return False, "Le champ 'plugins' doit être une liste"

        # Valider chaque configuration de plugin
        for i, plugin in enumerate(sequence['plugins']):
            plugin_valid, plugin_error = self._validate_plugin_config(plugin)
            if not plugin_valid:
                return False, f"Erreur dans la configuration du plugin #{i+1}: {plugin_error}"

        return True, ""

    def _validate_plugin_config(self, config: Any) -> Tuple[bool, str]:
        """
        Valide la configuration d'un plugin dans une séquence.
        
        Args:
            config: Configuration du plugin à valider
            
        Returns:
            Tuple (validité, message d'erreur)
        """
        # Accepter soit un dict (avec configuration), soit une chaîne (juste le nom)
        if isinstance(config, str):
            return True, ""
            
        if not isinstance(config, dict):
            return False, "La configuration du plugin doit être un dictionnaire ou une chaîne"

        if 'name' not in config:
            return False, "Le nom du plugin est requis"

        # Vérifier que les champs config/variables ont le bon format
        if 'config' in config and not isinstance(config['config'], dict):
            return False, "Le champ 'config' doit être un dictionnaire"
            
        if 'variables' in config and not isinstance(config['variables'], dict):
            return False, "Le champ 'variables' doit être un dictionnaire"

        # Vérifier les conditions si présentes
        if 'conditions' in config:
            if not isinstance(config['conditions'], list):
                return False, "Les conditions doivent être une liste"

            for i, condition in enumerate(config['conditions']):
                condition_valid, condition_error = self._validate_condition(condition)
                if not condition_valid:
                    return False, f"Erreur dans la condition #{i+1}: {condition_error}"

        return True, ""

    def _validate_condition(self, condition: Any) -> Tuple[bool, str]:
        """
        Valide une condition dans la configuration d'un plugin.
        
        Args:
            condition: Condition à valider
            
        Returns:
            Tuple (validité, message d'erreur)
        """
        if not isinstance(condition, dict):
            return False, "Une condition doit être un dictionnaire"
            
        required_fields = ['variable', 'operator', 'value']
        for field in required_fields:
            if field not in condition:
                return False, f"Champ requis manquant dans la condition: {field}"

        valid_operators = ['==', '!=', '>', '<', '>=', '<=', 'in', 'not in']
        if condition['operator'] not in valid_operators:
            return False, f"Opérateur invalide: {condition['operator']}"

        return True, ""

    def get_available_sequences(self) -> List[Dict[str, Any]]:
        """
        Récupère la liste des séquences disponibles.
        
        Returns:
            Liste des séquences avec leurs métadonnées
        """
        sequences = []
        
        if not self.sequences_dir.exists():
            logger.warning(f"Dossier des séquences non trouvé: {self.sequences_dir}")
            return sequences

        for seq_file in self.sequences_dir.glob('*.yml'):
            try:
                with open(seq_file, 'r', encoding='utf-8') as f:
                    sequence = yaml.load(f)
                    valid, _ = self.validate_sequence(sequence)
                    
                    if valid:
                        sequences.append({
                            'name': sequence.get('name', seq_file.stem),
                            'description': sequence.get('description', ''),
                            'file_name': seq_file.name,
                            'plugins_count': len(sequence.get('plugins', [])),
                            'modified': seq_file.stat().st_mtime  # Horodatage pour tri par date
                        })
                    else:
                        logger.warning(f"Séquence invalide ignorée: {seq_file.name}")
            except Exception as e:
                logger.error(f"Erreur lors du chargement de {seq_file.name}: {e}")

        # Tri par nom (insensible à la casse)
        return sorted(sequences, key=lambda x: x['name'].lower())
        
    def save_sequence(self, sequence_data: Dict[str, Any], file_path: Path) -> bool:
        """
        Sauvegarde une séquence dans un fichier YAML.
        
        Args:
            sequence_data: Données de la séquence à sauvegarder
            file_path: Chemin où sauvegarder le fichier
            
        Returns:
            True si la sauvegarde a réussi, False sinon
        """
        try:
            # Valider la séquence avant de la sauvegarder
            valid, error = self.validate_sequence(sequence_data)
            if not valid:
                logger.error(f"Impossible de sauvegarder une séquence invalide: {error}")
                return False
                
            # Créer le répertoire parent si nécessaire
            parent_dir = file_path.parent
            if not parent_dir.exists():
                parent_dir.mkdir(parents=True, exist_ok=True)
                
            # Sauvegarder la séquence
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(sequence_data, f)
                
            # Mettre à jour le cache
            self.sequence_cache[str(file_path)] = sequence_data
            logger.info(f"Séquence sauvegardée avec succès: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de la séquence: {e}")
            return False