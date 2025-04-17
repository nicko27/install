# install/plugins/plugins_utils/lvm.py
#!/usr/bin/env python3
"""
Fonctions utilitaires
"""

from plugins_utils.plugins_utils_base import PluginsUtilsBase
import os
import re
import json
from typing import Union, Optional, List, Dict, Any, Tuple

# Unités de taille LVM courantes
LVM_UNITS = {'k', 'm', 'g', 't', 'p', 'e'} # Kilo, Mega, Giga, Tera, Peta, Exa (puissances de 1024)

class UtilsCommands(PluginsUtilsBase):
    """
    Classe pour des fonctions utilitaires
    Hérite de PluginUtilsBase pour l'exécution de commandes.
    """

    def __init__(self, logger=None, target_ip=None):
        super().__init__(logger, target_ip)

    def get_options_dict(self,data):
        if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
            return data[0]
        elif isinstance(data, dict): # Au cas où ce serait déjà un dict
            return data
        return {} # Retourne un dict vide si ce n'est pas une liste [dict]

    def merge_dictionaries(self,*dictionaries):
        """
        Fusionne un nombre quelconque de dictionnaires en un nouveau dictionnaire.

        Les clés des dictionnaires fournis plus tard dans la séquence d'arguments
        écraseront les clés identiques des dictionnaires précédents.

        Args:
            *dictionaries: Une séquence de zéro, un ou plusieurs dictionnaires à fusionner.

        Returns:
            dict: Un nouveau dictionnaire contenant toutes les paires clé-valeur
                des dictionnaires d'entrée. Retourne un dictionnaire vide si
                aucun argument n'est fourni.

        Raises:
            TypeError: Si l'un des arguments fournis n'est pas un dictionnaire.
        """
        merged_result = {}
        for dictionary in dictionaries:
            # Vérifier que chaque argument est bien un dictionnaire
            if not isinstance(dictionary, dict):
                raise TypeError(f"Tous les arguments doivent être des dictionnaires. "
                                f"Reçu un argument de type: {type(dictionary)}")
            # Mettre à jour le dictionnaire résultat avec le contenu du dictionnaire actuel
            # update() gère l'écrasement des clés existantes
            merged_result.update(dictionary)
        return merged_result