"""
Utilitaires pour la gestion des adresses IP, notamment l'expansion des motifs et la gestion des exceptions.
"""

import re
import ipaddress
from typing import List, Set, Optional

def is_ip_match(ip: str, pattern: str) -> bool:
    """
    Vérifie si une adresse IP correspond à un motif.
    
    Args:
        ip: Adresse IP à vérifier
        pattern: Motif (peut contenir des *)
        
    Returns:
        bool: True si l'IP correspond au motif
    """
    # Convertir le motif en expression régulière
    regex_pattern = pattern.replace('.', '\\.').replace('*', '.*')
    return bool(re.match(f'^{regex_pattern}$', ip))

def expand_ip_pattern(pattern: str) -> List[str]:
    """
    Développe un motif d'adresse IP en liste d'adresses concrètes.
    
    Args:
        pattern: Motif d'adresse IP (peut contenir des *)
        
    Returns:
        List[str]: Liste des adresses IP correspondantes
    """
    # Si c'est une IP simple sans wildcard
    if '*' not in pattern:
        try:
            # Vérifier si c'est une IP valide
            ipaddress.ip_address(pattern)
            return [pattern]
        except ValueError:
            # Si ce n'est pas une IP valide, retourner une liste vide
            return []
    
    # Si c'est un motif avec wildcard
    parts = pattern.split('.')
    if len(parts) != 4:
        return []  # Format invalide
    
    # Générer toutes les combinaisons possibles
    result = []
    
    # Déterminer les plages pour chaque octet
    ranges = []
    for part in parts:
        if part == '*':
            ranges.append(range(0, 256))
        elif '-' in part:
            # Gestion des plages comme "1-5"
            try:
                start, end = map(int, part.split('-'))
                ranges.append(range(start, end + 1))
            except (ValueError, IndexError):
                return []  # Format invalide
        else:
            try:
                # Octet spécifique
                ranges.append([int(part)])
            except ValueError:
                return []  # Format invalide
    
    # Limiter le nombre d'IPs générées pour éviter des explosions combinatoires
    max_ips = 1000
    total_combinations = 1
    for r in ranges:
        total_combinations *= len(r)
    
    if total_combinations > max_ips:
        # Trop d'IPs à générer, retourner un échantillon représentatif
        # Par exemple, les 10 premières et les 10 dernières de chaque plage
        return [f"{ranges[0][0]}.{ranges[1][0]}.{ranges[2][0]}.{ranges[3][0]}",
                f"{ranges[0][-1]}.{ranges[1][-1]}.{ranges[2][-1]}.{ranges[3][-1]}"]
    
    # Générer toutes les combinaisons
    for a in ranges[0]:
        for b in ranges[1]:
            for c in ranges[2]:
                for d in ranges[3]:
                    result.append(f"{a}.{b}.{c}.{d}")
    
    return result

def get_target_ips(ip_list: str, exception_list: Optional[str] = None) -> List[str]:
    """
    Obtient la liste des adresses IP cibles en tenant compte des exceptions.
    
    Args:
        ip_list: Liste d'adresses IP séparées par des virgules (peut contenir des *)
        exception_list: Liste d'adresses IP à exclure (peut contenir des *)
        
    Returns:
        List[str]: Liste des adresses IP cibles
    """
    if not ip_list:
        return []
    
    # Développer toutes les adresses IP
    all_ips = set()
    for ip_pattern in ip_list.split(','):
        ip_pattern = ip_pattern.strip()
        if not ip_pattern:
            continue
            
        # Développer le motif
        expanded_ips = expand_ip_pattern(ip_pattern)
        all_ips.update(expanded_ips)
    
    # Si pas d'exceptions, retourner toutes les IPs
    if not exception_list:
        return list(all_ips)
    
    # Traiter les exceptions
    exception_patterns = [pattern.strip() for pattern in exception_list.split(',') if pattern.strip()]
    
    # Filtrer les IPs qui correspondent à au moins un motif d'exception
    result_ips = set()
    for ip in all_ips:
        # Vérifier si l'IP correspond à une exception
        is_exception = any(is_ip_match(ip, pattern) for pattern in exception_patterns)
        if not is_exception:
            result_ips.add(ip)
    
    return list(result_ips)
