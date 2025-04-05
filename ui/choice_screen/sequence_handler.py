"""
Gestionnaire de séquences pour l'écran de sélection.
Gère le chargement et la validation des séquences.
"""

from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple, Union
from ruamel.yaml import YAML
from ..utils.logging import get_logger
import os

logger = get_logger('sequence_handler')
yaml = YAML()

class SequenceHandler:
    """
    Gestionnaire de séquences pour l'écran de sélection.
    
    Cette classe est responsable de:
    - Charger les fichiers de séquence YAML
    - Valider la structure des séquences
    - Fournir les séquences disponibles
    - Sauvegarder les séquences
    """

    def __init__(self):
        """Initialise le gestionnaire de séquences"""
        self.sequences_dir = Path('sequences')
        self.sequence_cache = {}  # Cache pour les séquences chargées
        self.available_sequences_cache = None  # Cache pour la liste des séquences disponibles
        self.yaml = YAML()  # Instance YAML locale
        
        # Créer le dossier sequences s'il n'existe pas
        if not self.sequences_dir.exists():
            try:
                self.sequences_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Dossier de séquences créé: {self.sequences_dir}")
            except Exception as e:
                logger.error(f"Impossible de créer le dossier de séquences: {e}")
                
        logger.debug(f"Initialisation du gestionnaire de séquences: {self.sequences_dir}")

    def load_sequence(self, sequence_path: Union[str, Path]) -> Optional[Dict[str, Any]]:
        """
        Charge une séquence depuis un fichier YAML avec cache.
        
        Args:
            sequence_path: Chemin vers le fichier de séquence
            
        Returns:
            Dict[str, Any]: Données de la séquence ou None en cas d'erreur
        """
        # Convertir en Path si nécessaire
        if isinstance(sequence_path, str):
            sequence_path = Path(sequence_path)
        
        # Convertir en str pour l'utilisation comme clé de cache
        cache_key = str(sequence_path)
        
        # Vérifier d'abord dans le cache
        if cache_key in self.sequence_cache:
            logger.debug(f"Séquence trouvée dans le cache: {cache_key}")
            return self.sequence_cache[cache_key]
        
        try:
            if not sequence_path.exists():
                logger.error(f"Fichier de séquence non trouvé: {sequence_path}")
                return None

            with open(sequence_path, 'r', encoding='utf-8') as f:
                sequence = self.yaml.load(f)

            validation_result, error_message = self.validate_sequence(sequence)
            if not validation_result:
                logger.error(f"Séquence invalide ({sequence_path}): {error_message}")
                return None

            # Ajouter au cache
            self.sequence_cache[cache_key] = sequence
            logger.info(f"Séquence chargée et mise en cache: {sequence.get('name', 'Sans nom')}")
            return sequence

        except Exception as e:
            logger.error(f"Erreur lors du chargement de la séquence {sequence_path}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def validate_sequence(self, sequence: Any) -> Tuple[bool, str]:
        """
        Valide le format d'une séquence.
        
        Args:
            sequence: Données de la séquence à valider
            
        Returns:
            Tuple[bool, str]: Tuple (validité, message d'erreur)
        """
        if not isinstance(sequence, dict):
            return False, "La séquence doit être un dictionnaire"

        # Vérifier les champs requis
        required_fields = ['name', 'plugins']
        missing_fields = [field for field in required_fields if field not in sequence]
        if missing_fields:
            return False, f"Champs requis manquants: {', '.join(missing_fields)}"

        if not isinstance(sequence['plugins'], list):
            return False, "Le champ 'plugins' doit être une liste"

        # Valider chaque configuration de plugin
        for i, plugin in enumerate(sequence['plugins']):
            plugin_valid, plugin_error = self._validate_plugin_config(plugin)
            if not plugin_valid:
                return False, f"Erreur dans la configuration du plugin #{i+1}: {plugin_error}"

        # Ajouter automatiquement une description si manquante
        if 'description' not in sequence:
            sequence['description'] = f"Séquence {sequence['name']}"

        return True, ""

    def _validate_plugin_config(self, config: Any) -> Tuple[bool, str]:
        """
        Valide la configuration d'un plugin dans une séquence.
        
        Args:
            config: Configuration du plugin à valider
            
        Returns:
            Tuple[bool, str]: Tuple (validité, message d'erreur)
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
            Tuple[bool, str]: Tuple (validité, message d'erreur)
        """
        if not isinstance(condition, dict):
            return False, "Une condition doit être un dictionnaire"
            
        required_fields = ['variable', 'operator', 'value']
        missing_fields = [field for field in required_fields if field not in condition]
        if missing_fields:
            return False, f"Champs requis manquants dans la condition: {', '.join(missing_fields)}"

        valid_operators = ['==', '!=', '>', '<', '>=', '<=', 'in', 'not in']
        if condition['operator'] not in valid_operators:
            return False, f"Opérateur invalide: {condition['operator']}. Valeurs autorisées: {', '.join(valid_operators)}"

        return True, ""

    def get_available_sequences(self) -> List[Dict[str, Any]]:
        """
        Récupère la liste des séquences disponibles.
        Utilise un cache pour améliorer les performances lors d'appels répétés.
        
        Returns:
            List[Dict[str, Any]]: Liste des séquences avec leurs métadonnées
        """
        # Utiliser le cache si disponible
        if self.available_sequences_cache is not None:
            return self.available_sequences_cache
            
        sequences = []
        
        if not self.sequences_dir.exists():
            logger.warning(f"Dossier des séquences non trouvé: {self.sequences_dir}")
            self.available_sequences_cache = sequences
            return sequences

        for seq_file in self.sequences_dir.glob('*.yml'):
            try:
                # Essayer d'abord de récupérer depuis le cache
                if str(seq_file) in self.sequence_cache:
                    sequence = self.sequence_cache[str(seq_file)]
                    valid, _ = self.validate_sequence(sequence)
                else:
                    with open(seq_file, 'r', encoding='utf-8') as f:
                        sequence = self.yaml.load(f)
                        valid, _ = self.validate_sequence(sequence)
                    
                    # Ajouter au cache si valide
                    if valid:
                        self.sequence_cache[str(seq_file)] = sequence
                    
                if valid:
                    sequences.append({
                        'name': sequence.get('name', seq_file.stem),
                        'description': sequence.get('description', ''),
                        'file_name': seq_file.name,
                        'plugins_count': len(sequence.get('plugins', [])),
                        'shortcut': sequence.get('shortcut', ''),
                        'modified': seq_file.stat().st_mtime  # Horodatage pour tri par date
                    })
                else:
                    logger.warning(f"Séquence invalide ignorée: {seq_file.name}")
            except Exception as e:
                logger.error(f"Erreur lors du chargement de {seq_file.name}: {e}")

        # Tri par nom (insensible à la casse)
        sorted_sequences = sorted(sequences, key=lambda x: x['name'].lower())
        
        # Mettre en cache
        self.available_sequences_cache = sorted_sequences
        
        return sorted_sequences
        
    def save_sequence(self, sequence_data: Dict[str, Any], file_path: Path) -> bool:
        """
        Sauvegarde une séquence dans un fichier YAML.
        
        Args:
            sequence_data: Données de la séquence à sauvegarder
            file_path: Chemin où sauvegarder le fichier
            
        Returns:
            bool: True si la sauvegarde a réussi, False sinon
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
                self.yaml.dump(sequence_data, f)
                
            # Mettre à jour les caches
            self.sequence_cache[str(file_path)] = sequence_data
            # Invalider le cache des séquences disponibles
            self.available_sequences_cache = None
            
            logger.info(f"Séquence sauvegardée avec succès: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de la séquence: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
            
    def find_sequence_by_shortcut(self, shortcut: str) -> Tuple[Optional[Path], Optional[Dict[str, Any]]]:
        """
        Trouve une séquence par son shortcut.
        
        Args:
            shortcut: Le shortcut à rechercher
            
        Returns:
            Tuple: (chemin_sequence, données_sequence) ou (None, None) si non trouvé
        """
        matching_sequences = []
        
        # Parcourir les séquences disponibles
        for sequence_info in self.get_available_sequences():
            file_name = sequence_info['file_name']
            seq_path = self.sequences_dir / file_name
            
            # Vérifier si cette séquence a le shortcut recherché
            shortcuts = sequence_info.get('shortcut', '')
            
            if isinstance(shortcuts, str) and shortcuts == shortcut:
                matching_sequences.append((seq_path, self.sequence_cache.get(str(seq_path))))
            elif isinstance(shortcuts, list) and shortcut in shortcuts:
                matching_sequences.append((seq_path, self.sequence_cache.get(str(seq_path))))
        
        if len(matching_sequences) == 0:
            logger.error(f"Aucune séquence trouvée avec le shortcut '{shortcut}'")
            return None, None
        elif len(matching_sequences) > 1:
            logger.error(f"Plusieurs séquences trouvées avec le shortcut '{shortcut}':")
            for seq_path, _ in matching_sequences:
                logger.error(f"- {seq_path.name}")
            return None, None
        else:
            # Si la séquence n'est pas déjà en cache, la charger
            seq_path, seq_data = matching_sequences[0]
            if seq_data is None:
                seq_data = self.load_sequence(seq_path)
            return seq_path, seq_data
            
    def clear_cache(self) -> None:
        """
        Vide les caches des séquences.
        Utile après des modifications ou pour les tests.
        """
        self.sequence_cache.clear()
        self.available_sequences_cache = None
        logger.debug("Caches des séquences vidés")