from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger('plugin_instance')

@dataclass
class PluginInstance:
    """Représente une instance de plugin avec sa configuration"""
    name: str
    instance_id: int
    config: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def unique_id(self) -> str:
        """Identifiant unique de l'instance"""
        return f"{self.name}_{self.instance_id}"
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """Met à jour la configuration du plugin"""
        # Toujours stocker dans un sous-dictionnaire 'config'
        if 'config' in new_config:
            self.config = new_config['config']
        elif 'variables' in new_config:
            # Convertir l'ancien format
            self.config = new_config['variables']
        else:
            # Prendre toutes les clés sauf les métadonnées
            self.config = {k: v for k, v in new_config.items() 
                         if k not in {'plugin_name', 'instance_id', 'show_name', 'icon', 'remote_execution'}}
        logger.debug(f"Config mise à jour pour {self.unique_id}: {self.config}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'instance en dictionnaire pour la sérialisation"""
        return {
            'name': self.name,
            'config': self.config
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], instance_id: int) -> 'PluginInstance':
        """Crée une instance depuis un dictionnaire"""
        name = data['name']
        config = {}
        if 'config' in data:
            config = data['config']
        elif 'variables' in data:
            config = data['variables']
        return cls(name=name, instance_id=instance_id, config=config)
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PluginInstance):
            return NotImplemented
        return (self.name == other.name and 
                self.instance_id == other.instance_id and 
                self.config == other.config)
