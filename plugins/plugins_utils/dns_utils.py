# install/plugins/plugins_utils/dns_utils.py
#!/usr/bin/env python3
"""
Module utilitaire pour effectuer des requêtes DNS.
Utilise la bibliothèque dnspython pour des requêtes détaillées.
NOTE: Nécessite l'installation du paquet pip 'dnspython'.
"""

from .plugin_utils_base import PluginUtilsBase
from typing import Union, Optional, List, Dict, Any, Tuple

# Essayer d'importer dnspython et ses composants
try:
    import dns.resolver
    import dns.reversename
    import dns.exception
    DNSPYTHON_AVAILABLE = True
except ImportError:
    DNSPYTHON_AVAILABLE = False
    # Définir des exceptions factices si dnspython n'est pas installé
    # pour éviter les erreurs à l'exécution si les méthodes ne sont pas appelées.
    class DNSException(Exception): pass
    class NXDOMAIN(DNSException): pass
    class Timeout(DNSException): pass
    class NoAnswer(DNSException): pass
    class NoNameservers(DNSException): pass
    # Simuler les objets nécessaires pour que les signatures de méthodes soient valides
    class dns:
        class resolver:
            @staticmethod
            def Resolver(): return None
            @staticmethod
            def NXDOMAIN(*args, **kwargs): return NXDOMAIN(*args, **kwargs)
            @staticmethod
            def Timeout(*args, **kwargs): return Timeout(*args, **kwargs)
            @staticmethod
            def NoAnswer(*args, **kwargs): return NoAnswer(*args, **kwargs)
            @staticmethod
            def NoNameservers(*args, **kwargs): return NoNameservers(*args, **kwargs)
        class reversename:
            @staticmethod
            def from_address(addr): return addr # Simuler
        class exception:
            DNSException = DNSException
            NXDOMAIN = NXDOMAIN
            Timeout = Timeout
            NoAnswer = NoAnswer
            NoNameservers = NoNameservers


class DnsUtils(PluginUtilsBase):
    """
    Classe pour effectuer des requêtes DNS via la bibliothèque dnspython.
    Hérite de PluginUtilsBase pour la journalisation.
    """

    DEFAULT_TIMEOUT = 2.0 # Secondes

    def __init__(self, logger=None, target_ip=None):
        """Initialise le gestionnaire DNS."""
        super().__init__(logger, target_ip)
        if not DNSPYTHON_AVAILABLE:
            self.log_error("Le module 'dnspython' est requis mais n'a pas pu être importé. "
                           "Les opérations DNS échoueront. Installez-le via pip.")
            # raise ImportError("Le module dnspython est nécessaire.")

    def _get_resolver(self, nameservers: Optional[List[str]] = None, timeout: Optional[float] = None) -> Optional[dns.resolver.Resolver]:
        """Crée et configure un objet Resolver dnspython."""
        if not DNSPYTHON_AVAILABLE: return None

        resolver = dns.resolver.Resolver()
        resolver.timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT
        resolver.lifetime = resolver.timeout # Durée totale de la tentative de résolution

        if nameservers:
            resolver.nameservers = nameservers
            self.log_debug(f"Utilisation des serveurs DNS spécifiés: {nameservers}")
        else:
            # Utiliser les serveurs DNS système par défaut
            self.log_debug(f"Utilisation des serveurs DNS système (timeout={resolver.lifetime}s)")
            # Note: dnspython essaie de lire /etc/resolv.conf par défaut

        return resolver

    def _query(self, resolver: dns.resolver.Resolver, qname: str, rdtype: Union[str, int]) -> Optional[dns.resolver.Answer]:
        """Effectue une requête DNS et gère les exceptions courantes."""
        if not DNSPYTHON_AVAILABLE: return None
        try:
            return resolver.resolve(qname, rdtype, raise_on_no_answer=False)
        except dns.resolver.NXDOMAIN:
            self.log_info(f"Le domaine '{qname}' n'existe pas (NXDOMAIN).")
            return None
        except dns.resolver.Timeout:
            self.log_warning(f"Timeout lors de la requête DNS pour '{qname}' (type {rdtype}).")
            return None
        except dns.resolver.NoNameservers as e:
            self.log_error(f"Aucun serveur DNS n'a pu être contacté pour '{qname}': {e}")
            return None
        except dns.resolver.NoAnswer:
            self.log_info(f"Aucune réponse (NoAnswer) pour '{qname}' (type {rdtype}).")
            return None
        except dns.exception.DNSException as e:
            self.log_error(f"Erreur DNS inattendue pour '{qname}' (type {rdtype}): {e}")
            return None
        except Exception as e:
            self.log_error(f"Erreur non-DNS lors de la requête pour '{qname}': {e}", exc_info=True)
            return None

    def resolve_a(self, hostname: str, nameservers: Optional[List[str]] = None, timeout: Optional[float] = None) -> List[str]:
        """Résout les enregistrements A (IPv4) pour un nom d'hôte."""
        self.log_info(f"Résolution A pour: {hostname}")
        resolver = self._get_resolver(nameservers, timeout)
        if not resolver: return []

        answer = self._query(resolver, hostname, 'A')
        ips = [str(rdata) for rdata in answer] if answer else []
        self.log_info(f"  Résultats A: {ips if ips else 'Aucun'}")
        return ips

    def resolve_aaaa(self, hostname: str, nameservers: Optional[List[str]] = None, timeout: Optional[float] = None) -> List[str]:
        """Résout les enregistrements AAAA (IPv6) pour un nom d'hôte."""
        self.log_info(f"Résolution AAAA pour: {hostname}")
        resolver = self._get_resolver(nameservers, timeout)
        if not resolver: return []

        answer = self._query(resolver, hostname, 'AAAA')
        ips = [str(rdata) for rdata in answer] if answer else []
        self.log_info(f"  Résultats AAAA: {ips if ips else 'Aucun'}")
        return ips

    def resolve_mx(self, domain: str, nameservers: Optional[List[str]] = None, timeout: Optional[float] = None) -> List[Tuple[int, str]]:
        """Résout les enregistrements MX (Mail Exchanger) pour un domaine."""
        self.log_info(f"Résolution MX pour: {domain}")
        resolver = self._get_resolver(nameservers, timeout)
        if not resolver: return []

        answer = self._query(resolver, domain, 'MX')
        # Format rdata pour MX: preference, exchange
        mx_records = sorted([(rdata.preference, str(rdata.exchange)) for rdata in answer], key=lambda x: x[0]) if answer else []
        self.log_info(f"  Résultats MX: {mx_records if mx_records else 'Aucun'}")
        return mx_records

    def resolve_txt(self, domain: str, nameservers: Optional[List[str]] = None, timeout: Optional[float] = None) -> List[str]:
        """Résout les enregistrements TXT pour un domaine."""
        self.log_info(f"Résolution TXT pour: {domain}")
        resolver = self._get_resolver(nameservers, timeout)
        if not resolver: return []

        answer = self._query(resolver, domain, 'TXT')
        # Les enregistrements TXT peuvent être segmentés, dnspython les retourne comme liste de bytes.
        # Il faut les joindre et les décoder.
        txt_records = []
        if answer:
            for rdata in answer:
                # rdata.strings est un tuple de bytes (b'part1', b'part2')
                full_txt = b"".join(rdata.strings).decode('utf-8', errors='replace')
                txt_records.append(full_txt)

        self.log_info(f"  Résultats TXT: {txt_records if txt_records else 'Aucun'}")
        return txt_records

    def resolve_srv(self, service: str, proto: str = 'tcp', domain: str = '', nameservers: Optional[List[str]] = None, timeout: Optional[float] = None) -> List[Tuple[int, int, int, str]]:
        """
        Résout les enregistrements SRV pour un service.

        Args:
            service: Nom du service (ex: _ldap).
            proto: Protocole (tcp ou udp).
            domain: Domaine où chercher le service (si vide, utilise le domaine local).
            nameservers: Serveurs DNS à utiliser.
            timeout: Timeout.

        Returns:
            Liste de tuples (priority, weight, port, target) triée par priorité puis poids.
        """
        query_name = f"_{service}._{proto}.{domain}"
        self.log_info(f"Résolution SRV pour: {query_name}")
        resolver = self._get_resolver(nameservers, timeout)
        if not resolver: return []

        answer = self._query(resolver, query_name, 'SRV')
        # Format rdata pour SRV: priority, weight, port, target
        srv_records = sorted([
            (rdata.priority, rdata.weight, rdata.port, str(rdata.target).rstrip('.')) # Nettoyer le '.' final
            for rdata in answer
        ], key=lambda x: (x[0], -x[1])) if answer else [] # Tri par priorité (asc), puis poids (desc)

        self.log_info(f"  Résultats SRV: {srv_records if srv_records else 'Aucun'}")
        return srv_records

    def resolve_ptr(self, ip_address: str, nameservers: Optional[List[str]] = None, timeout: Optional[float] = None) -> List[str]:
        """
        Effectue une résolution DNS inverse (PTR) pour une adresse IP.

        Args:
            ip_address: Adresse IP (v4 ou v6).
            nameservers: Serveurs DNS à utiliser.
            timeout: Timeout.

        Returns:
            Liste des noms d'hôtes trouvés.
        """
        if not DNSPYTHON_AVAILABLE: return []
        self.log_info(f"Résolution PTR (inverse) pour: {ip_address}")
        resolver = self._get_resolver(nameservers, timeout)
        if not resolver: return []

        try:
            # Construire le nom de domaine inverse (ex: 1.2.168.192.in-addr.arpa.)
            rev_name = dns.reversename.from_address(ip_address)
            self.log_debug(f"  Nom inverse généré: {rev_name}")
            answer = self._query(resolver, rev_name, 'PTR')
            # Nettoyer le '.' final des noms d'hôtes
            hostnames = [str(rdata).rstrip('.') for rdata in answer] if answer else []
            self.log_info(f"  Résultats PTR: {hostnames if hostnames else 'Aucun'}")
            return hostnames
        except dns.exception.SyntaxError:
             self.log_error(f"Adresse IP invalide pour la résolution inverse: {ip_address}")
             return []
        except Exception as e:
             self.log_error(f"Erreur lors de la résolution inverse pour {ip_address}: {e}", exc_info=True)
             return []

    def get_host_ips(self, hostname: str, include_ipv6: bool = True, **kwargs) -> List[str]:
        """Retourne les adresses IPv4 et optionnellement IPv6 d'un nom d'hôte."""
        ips = self.resolve_a(hostname, **kwargs)
        if include_ipv6:
            ips.extend(self.resolve_aaaa(hostname, **kwargs))
        return ips

    def get_host_by_ip(self, ip_address: str, **kwargs) -> Optional[str]:
        """Retourne le premier nom d'hôte trouvé pour une adresse IP."""
        hostnames = self.resolve_ptr(ip_address, **kwargs)
        return hostnames[0] if hostnames else None

