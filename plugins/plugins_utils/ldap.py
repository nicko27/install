# install/plugins/plugins_utils/ldap.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module utilitaire pour interagir avec des annuaires LDAP.
Utilise la bibliothèque python-ldap pour une interaction robuste.
NOTE: Nécessite l'installation du paquet pip 'python-ldap' et de ses dépendances système.
"""

from .plugin_utils_base import PluginUtilsBase
import os
import time
from typing import Union, Optional, List, Dict, Any, Tuple, Generator

# Essayer d'importer ldap et ses composants
try:
    import ldap
    import ldap.modlist as modlist
    # Importer les exceptions spécifiques pour une meilleure gestion
    from ldap import LDAPError, INVALID_CREDENTIALS, NO_SUCH_OBJECT, ALREADY_EXISTS, TYPE_OR_VALUE_EXISTS, SERVER_DOWN, SIZELIMIT_EXCEEDED, NO_SUCH_ATTRIBUTE, NOT_ALLOWED_ON_NONLEAF, REFERRAL
    LDAP_AVAILABLE = True
except ImportError:
    LDAP_AVAILABLE = False
    # Définir des exceptions factices si ldap n'est pas installé
    # pour que le reste du code puisse être analysé sans erreur immédiate
    class LDAPError(Exception): pass
    class INVALID_CREDENTIALS(LDAPError): pass
    class NO_SUCH_OBJECT(LDAPError): pass
    class ALREADY_EXISTS(LDAPError): pass
    class TYPE_OR_VALUE_EXISTS(LDAPError): pass
    class SERVER_DOWN(LDAPError): pass
    class SIZELIMIT_EXCEEDED(LDAPError): pass
    class NO_SUCH_ATTRIBUTE(LDAPError): pass
    class NOT_ALLOWED_ON_NONLEAF(LDAPError): pass
    class REFERRAL(LDAPError): pass
    modlist = None # type: ignore

class LdapCommands(PluginUtilsBase):
    """
    Classe pour interagir avec LDAP via la bibliothèque python-ldap.
    Hérite de PluginUtilsBase pour la journalisation.
    """

    DEFAULT_PORT = 389
    DEFAULT_LDAPS_PORT = 636

    def __init__(self, logger=None, target_ip=None):
        """Initialise le gestionnaire LDAP."""
        super().__init__(logger, target_ip)
        if not LDAP_AVAILABLE:
            self.log_error("Le module 'python-ldap' est requis mais n'a pas pu être importé. "
                           "Les opérations LDAP échoueront. Installer via pip et vérifier les dépendances système (ex: libldap2-dev, libsasl2-dev).")
            # On pourrait lever une exception ici pour signaler clairement le problème
            # raise ImportError("Le module python-ldap est nécessaire.")

    def _connect(self,
                 server: str,
                 port: Optional[int] = None,
                 use_tls: bool = False,
                 use_starttls: bool = False,
                 bind_dn: Optional[str] = None,
                 password: Optional[str] = None,
                 timeout: int = 10,
                 ca_cert_file: Optional[str] = None) -> Optional[ldap.ldapobject.SimpleLDAPObject]:
        """
        Établit une connexion et effectue l'authentification (bind) avec le serveur LDAP.

        Args:
            server: Adresse du serveur LDAP.
            port: Port du serveur (défaut 389 ou 636 si use_tls).
            use_tls: Utiliser LDAPS (connexion SSL/TLS directe).
            use_starttls: Utiliser STARTTLS (met à niveau une connexion non chiffrée).
            bind_dn: DN pour l'authentification (None pour anonyme).
            password: Mot de passe pour l'authentification.
            timeout: Timeout de connexion en secondes.
            ca_cert_file: Chemin vers le fichier de certificat CA pour la validation TLS (optionnel).

        Returns:
            Objet de connexion LDAP ou None si échec.
        """
        if not LDAP_AVAILABLE: return None

        proto = "ldap://"
        if use_tls:
            proto = "ldaps://"
            conn_port = port or self.DEFAULT_LDAPS_PORT
        else:
            conn_port = port or self.DEFAULT_PORT

        uri = f"{proto}{server}:{conn_port}"
        self.log_info(f"Connexion à l'annuaire LDAP: {uri}")

        conn: Optional[ldap.ldapobject.SimpleLDAPObject] = None # Initialiser conn à None
        try:
            # Initialiser la connexion
            conn = ldap.initialize(uri, trace_level=0) # trace_level=1 pour debug
            conn.set_option(ldap.OPT_NETWORK_TIMEOUT, float(timeout))
            conn.set_option(ldap.OPT_PROTOCOL_VERSION, ldap.VERSION3)
            # Gérer les références (referrals) - souvent nécessaire avec AD
            # ldap.OPT_REFERRALS (0 ou 1). 0 = ne pas suivre.
            conn.set_option(ldap.OPT_REFERRALS, 0)

            # Configuration TLS/Certificat
            if use_tls or use_starttls:
                tls_options = ldap.OPT_X_TLS_HARD if ca_cert_file else ldap.OPT_X_TLS_ALLOW
                conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, tls_options)
                if ca_cert_file:
                    if os.path.exists(ca_cert_file):
                        conn.set_option(ldap.OPT_X_TLS_CACERTFILE, ca_cert_file)
                        self.log_debug(f"Utilisation du certificat CA: {ca_cert_file}")
                    else:
                         self.log_error(f"Fichier certificat CA introuvable: {ca_cert_file}")
                         return None # Échec si CA spécifié mais non trouvé
                else:
                    self.log_warning("Aucun fichier CA fourni, connexion TLS/STARTTLS autorisera les certificats auto-signés.")

                # Forcer TLSv1.2+ si possible
                try:
                    conn.set_option(ldap.OPT_X_TLS_PROTOCOL_MIN, ldap.OPT_X_TLS_PROTOCOL_TLS1_2)
                except AttributeError:
                     self.log_debug("Option OPT_X_TLS_PROTOCOL_MIN non disponible (ancienne version python-ldap/openldap?).")
                # Désactiver la réutilisation de session TLS si elle pose problème (rare)
                # conn.set_option(ldap.OPT_X_TLS_NEVER, True)

            # Démarrer STARTTLS si demandé et non déjà en LDAPS
            if use_starttls and not use_tls:
                self.log_info("Négociation STARTTLS...")
                # Utiliser start_tls_s() pour une opération synchrone
                conn.start_tls_s()
                self.log_info("STARTTLS établi avec succès.")

            # Authentification (Bind)
            if bind_dn:
                if password is None: password = "" # Utiliser mot de passe vide si None
                self.log_info(f"Authentification en tant que: {bind_dn}")
                # Utiliser simple_bind_s pour une opération synchrone
                conn.simple_bind_s(bind_dn, password)
                self.log_info("Authentification réussie.")
            else:
                self.log_info("Connexion anonyme (pas de bind DN fourni).")
                # Essayer un bind anonyme explicite
                conn.simple_bind_s("", "")

            return conn

        except INVALID_CREDENTIALS:
            self.log_error(f"Échec de l'authentification LDAP pour {bind_dn or 'anonyme'}: Identifiants invalides.")
            if conn: conn.unbind_s()
            return None
        except SERVER_DOWN as e:
             self.log_error(f"Serveur LDAP inaccessible ({uri}): {e}")
             if conn: conn.unbind_s()
             return None
        except LDAPError as e:
            # Capturer d'autres erreurs LDAP spécifiques si nécessaire
            self.log_error(f"Erreur LDAP lors de la connexion/bind ({uri}): {e}")
            if conn: conn.unbind_s()
            return None
        except Exception as e:
            self.log_error(f"Erreur inattendue lors de la connexion LDAP ({uri}): {e}", exc_info=True)
            if conn:
                 try: conn.unbind_s()
                 except: pass
            return None

    def _decode_ldap_values(self, attrs: Dict[bytes, List[bytes]]) -> Dict[str, Union[str, List[str]]]:
        """Décode les clés et valeurs bytes d'un dictionnaire d'attributs LDAP en str."""
        decoded_attrs = {}
        for key_bytes, values_bytes in attrs.items():
            try:
                key_str = key_bytes.decode('utf-8', errors='replace')
            except AttributeError: # Si la clé est déjà une chaîne (rare)
                 key_str = str(key_bytes)

            decoded_values = []
            for v_bytes in values_bytes:
                 try:
                     decoded_values.append(v_bytes.decode('utf-8', errors='replace'))
                 except AttributeError: # Si la valeur est déjà une chaîne
                      decoded_values.append(str(v_bytes))

            # Si une seule valeur, ne pas retourner une liste
            decoded_attrs[key_str] = decoded_values[0] if len(decoded_values) == 1 else decoded_values
        return decoded_attrs

    def search(self,
               base_dn: str,
               scope_str: str = 'SUBTREE', # BASE, ONELEVEL, SUBTREE
               filter_str: str = '(objectClass=*)',
               attributes: Optional[List[str]] = None,
               # Paramètres de connexion passés via **conn_kwargs
               timeout: int = 10,
               sizelimit: int = 0, # 0 = illimité
               **conn_kwargs) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Effectue une recherche LDAP.

        Args:
            base_dn: DN de base.
            scope_str: Étendue ('BASE', 'ONELEVEL', 'SUBTREE').
            filter_str: Filtre LDAP.
            attributes: Attributs à retourner (None pour tous les attributs utilisateur).
            timeout: Timeout spécifique pour cette opération de recherche.
            sizelimit: Nombre maximum d'entrées à retourner (0 = illimité).
            **conn_kwargs: Arguments pour la connexion (_connect: server, port, bind_dn, password, etc.).

        Returns:
            Tuple (succès: bool, résultats: List[Dict]).
            Chaque dict contient 'dn' et les attributs décodés.
        """
        if not LDAP_AVAILABLE: return False, []

        scope_map = {
            'BASE': ldap.SCOPE_BASE,
            'ONELEVEL': ldap.SCOPE_ONELEVEL,
            'SUBTREE': ldap.SCOPE_SUBTREE
        }
        scope = scope_map.get(scope_str.upper(), ldap.SCOPE_SUBTREE)

        self.log_info(f"Recherche LDAP: base='{base_dn}', scope='{scope_str}', filter='{filter_str}'")
        # Passer le timeout spécifique à _connect si nécessaire, sinon il utilisera sa propre valeur par défaut
        conn_kwargs.setdefault('timeout', timeout)
        conn = self._connect(**conn_kwargs)
        if not conn:
            return False, []

        results_list = []
        try:
            # Définir le timeout pour l'opération de recherche elle-même
            # search_ext_s permet de définir un timeout spécifique pour la recherche
            # attrlist=None signifie récupérer tous les attributs utilisateur ('*')
            # attrsonly=0 signifie récupérer attributs et valeurs
            ldap_results = conn.search_ext_s(base=base_dn,
                                             scope=scope,
                                             filterstr=filter_str.encode('utf-8'), # Le filtre doit être en bytes
                                             attrlist=attributes, # Peut être None ou liste de str
                                             attrsonly=0,
                                             timeout=timeout,
                                             sizelimit=sizelimit)

            for dn_bytes, attrs_bytes in ldap_results:
                if dn_bytes: # Ignorer les références potentielles (dn=None)
                    dn_str = dn_bytes.decode('utf-8', errors='replace')
                    decoded_attrs = self._decode_ldap_values(attrs_bytes)
                    results_list.append({'dn': dn_str, **decoded_attrs}) # Ajouter le DN au dictionnaire

            self.log_info(f"Recherche LDAP terminée, {len(results_list)} entrée(s) trouvée(s).")
            self.log_debug(f"Résultats LDAP: {results_list}")
            return True, results_list

        except NO_SUCH_OBJECT:
            self.log_info(f"La base de recherche '{base_dn}' n'existe pas.")
            return True, [] # Pas une erreur, juste aucun résultat
        except SIZELIMIT_EXCEEDED:
             self.log_warning(f"Limite de taille ({sizelimit}) atteinte pour la recherche LDAP.")
             # search_ext_s lève l'exception, les résultats partiels ne sont pas retournés directement.
             # Pour les obtenir, il faudrait utiliser search_ext avec un callback.
             return False, [] # Indiquer un échec partiel
        except LDAPError as e:
            self.log_error(f"Erreur LDAP pendant la recherche: {e}")
            return False, []
        except Exception as e:
             self.log_error(f"Erreur inattendue pendant la recherche LDAP: {e}", exc_info=True)
             return False, []
        finally:
            if conn: conn.unbind_s()

    def add(self, dn: str, attrs: Dict[str, Union[str, List[str]]], **conn_kwargs) -> bool:
        """
        Ajoute une nouvelle entrée LDAP.

        Args:
            dn: Distinguished Name de la nouvelle entrée.
            attrs: Dictionnaire des attributs {nom_attr: valeur ou [valeurs]}.
                   Les valeurs peuvent être str ou List[str]. Elles seront encodées en UTF-8.
            **conn_kwargs: Arguments pour la connexion (_connect).

        Returns:
            bool: True si succès.
        """
        if not LDAP_AVAILABLE or modlist is None: return False

        self.log_info(f"Ajout de l'entrée LDAP: {dn}")
        conn = self._connect(**conn_kwargs)
        if not conn: return False

        # Construire le modlist pour ldap.add_s (liste de tuples (type_attr_bytes, valeurs_attr_bytes))
        add_modlist = []
        try:
            for key, value in attrs.items():
                key_bytes = key.encode('utf-8')
                values_bytes: List[bytes]
                if isinstance(value, list):
                    values_bytes = [str(v).encode('utf-8') for v in value] # Assurer str avant encode
                elif isinstance(value, str):
                    values_bytes = [value.encode('utf-8')]
                elif isinstance(value, bytes):
                     values_bytes = [value] # Déjà en bytes
                else:
                    values_bytes = [str(value).encode('utf-8')] # Tenter conversion str

                # Vérifier que les valeurs ne sont pas vides (souvent invalide pour add)
                if not all(values_bytes):
                     self.log_warning(f"Attribut '{key}' contient une valeur vide, ignoré pour l'ajout.")
                     continue

                add_modlist.append((key_bytes, values_bytes))

        except Exception as e_build:
             self.log_error(f"Erreur lors de la construction du modlist pour l'ajout: {e_build}", exc_info=True)
             conn.unbind_s(); return False

        if not add_modlist:
             self.log_error("Aucun attribut valide à ajouter.")
             conn.unbind_s(); return False

        self.log_debug(f"Modlist d'ajout pour {dn}: {add_modlist}")
        try:
            # Utiliser add_s pour une opération synchrone
            conn.add_s(dn, add_modlist)
            self.log_success(f"Entrée LDAP '{dn}' ajoutée avec succès.")
            return True
        except ALREADY_EXISTS:
            self.log_error(f"Échec de l'ajout: L'entrée LDAP '{dn}' existe déjà.")
            return False
        except LDAPError as e:
            self.log_error(f"Erreur LDAP lors de l'ajout de '{dn}': {e}")
            # Afficher plus de détails si disponibles dans l'exception
            if hasattr(e, 'args') and e.args:
                 try:
                      err_info = e.args[0]
                      if isinstance(err_info, dict):
                           self.log_error(f"  Info serveur: {err_info.get('info')}, Description: {err_info.get('desc')}")
                 except: pass
            return False
        except Exception as e:
            self.log_error(f"Erreur inattendue lors de l'ajout LDAP: {e}", exc_info=True)
            return False
        finally:
            if conn: conn.unbind_s()

    def modify(self, dn: str, changes: Dict[str, Dict[str, Union[str, List[str]]]], **conn_kwargs) -> bool:
        """
        Modifie une entrée LDAP existante.

        Args:
            dn: DN de l'entrée à modifier.
            changes: Dictionnaire décrivant les changements. Format:
                     {
                         'add': { 'attr1': 'val1', 'attr2': ['valA', 'valB'] },
                         'delete': { 'attr3': None, 'attr4': 'val_to_remove' }, # None supprime tout l'attribut
                         'replace': { 'attr5': 'new_val', 'attr6': ['new1', 'new2'] }
                     }
                     Les valeurs peuvent être str ou List[str]. Elles seront encodées en UTF-8.
            **conn_kwargs: Arguments pour la connexion (_connect).

        Returns:
            bool: True si succès.
        """
        if not LDAP_AVAILABLE or modlist is None: return False

        self.log_info(f"Modification de l'entrée LDAP: {dn}")
        conn = self._connect(**conn_kwargs)
        if not conn: return False

        # Construire le modlist pour ldap.modify_s
        ldap_modlist = []
        try:
            for op_str, attrs in changes.items():
                op_map = {'add': ldap.MOD_ADD, 'delete': ldap.MOD_DELETE, 'replace': ldap.MOD_REPLACE}
                op = op_map.get(op_str.lower())
                if op is None:
                    self.log_error(f"Opération de modification inconnue: {op_str}")
                    conn.unbind_s(); return False

                for attr, value in attrs.items():
                    attr_bytes = attr.encode('utf-8')
                    values_bytes: Optional[List[bytes]] = [] # Liste vide par défaut

                    # Pour MOD_DELETE, None signifie supprimer tout l'attribut
                    if op == ldap.MOD_DELETE and value is None:
                         values_bytes = None # Mettre à None pour MOD_DELETE de l'attribut entier
                    elif value is not None:
                        # Convertir la valeur ou la liste de valeurs en liste de bytes
                        temp_values_bytes: List[bytes] = []
                        if isinstance(value, list):
                            temp_values_bytes = [str(v).encode('utf-8') for v in value]
                        elif isinstance(value, str):
                            temp_values_bytes = [value.encode('utf-8')]
                        elif isinstance(value, bytes):
                             temp_values_bytes = [value]
                        else:
                            temp_values_bytes = [str(value).encode('utf-8')]
                        # Filtrer les valeurs vides potentielles (sauf si MOD_REPLACE avec liste vide est intentionnel)
                        values_bytes = [v for v in temp_values_bytes if v]
                        if not values_bytes and op != ldap.MOD_REPLACE:
                             self.log_warning(f"Tentative d'opération '{op_str}' sur '{attr}' avec une valeur vide, ignoré.")
                             continue # Ne pas ajouter d'opération avec valeur vide (sauf pour replace)

                    # Ajouter l'opération à la liste
                    ldap_modlist.append((op, attr_bytes, values_bytes))

        except Exception as e_build:
             self.log_error(f"Erreur lors de la construction du modlist pour la modification: {e_build}", exc_info=True)
             conn.unbind_s(); return False

        if not ldap_modlist:
            self.log_warning("Aucune modification valide à appliquer.")
            conn.unbind_s(); return True # Pas d'erreur si rien à faire

        self.log_debug(f"Modlist de modification pour {dn}: {ldap_modlist}")
        try:
            # Utiliser modify_s pour une opération synchrone
            conn.modify_s(dn, ldap_modlist)
            self.log_success(f"Entrée LDAP '{dn}' modifiée avec succès.")
            return True
        except NO_SUCH_OBJECT:
            self.log_error(f"Échec de la modification: L'entrée LDAP '{dn}' n'existe pas.")
            return False
        except TYPE_OR_VALUE_EXISTS:
             # Souvent pour MOD_ADD si la valeur existe déjà
             self.log_warning(f"Échec partiel de la modification pour '{dn}': Type ou valeur existe déjà (peut être normal pour MOD_ADD).")
             # Considérer comme succès partiel ? Pour l'instant, on retourne True.
             return True
        except NO_SUCH_ATTRIBUTE:
             # Souvent pour MOD_DELETE si l'attribut/valeur n'existe pas
             self.log_warning(f"Échec partiel de la modification pour '{dn}': Attribut ou valeur à supprimer n'existe pas (peut être normal pour MOD_DELETE).")
             return True # Considérer comme succès car état final atteint
        except LDAPError as e:
            self.log_error(f"Erreur LDAP lors de la modification de '{dn}': {e}")
            if hasattr(e, 'args') and e.args:
                 try:
                      err_info = e.args[0]
                      if isinstance(err_info, dict):
                           self.log_error(f"  Info serveur: {err_info.get('info')}, Description: {err_info.get('desc')}")
                 except: pass
            return False
        except Exception as e:
            self.log_error(f"Erreur inattendue lors de la modification LDAP: {e}", exc_info=True)
            return False
        finally:
            if conn: conn.unbind_s()

    def delete(self, dn: str, recursive: bool = False, **conn_kwargs) -> bool:
        """
        Supprime une entrée LDAP.

        Args:
            dn: DN de l'entrée à supprimer.
            recursive: Si True, tente de supprimer récursivement (NON IMPLÉMENTÉ de manière fiable ici).
            **conn_kwargs: Arguments pour la connexion (_connect).

        Returns:
            bool: True si succès ou si l'entrée n'existait pas.
        """
        if not LDAP_AVAILABLE: return False

        if recursive:
             self.log_error("La suppression récursive n'est pas implémentée de manière fiable dans cette fonction.")
             self.log_warning("Tentative de suppression simple de l'entrée racine uniquement.")

        self.log_info(f"Suppression de l'entrée LDAP: {dn}")
        conn = self._connect(**conn_kwargs)
        if not conn: return False

        try:
            # Utiliser delete_s pour une opération synchrone
            conn.delete_s(dn)
            self.log_success(f"Entrée LDAP '{dn}' supprimée avec succès.")
            return True
        except NO_SUCH_OBJECT:
            self.log_warning(f"L'entrée LDAP '{dn}' n'existe pas (ou plus). Suppression considérée comme réussie.")
            return True
        except NOT_ALLOWED_ON_NONLEAF:
             self.log_error(f"Échec de la suppression: L'entrée '{dn}' n'est pas une feuille (contient des enfants). Suppression récursive non supportée.")
             return False
        except LDAPError as e:
            self.log_error(f"Erreur LDAP lors de la suppression de '{dn}': {e}")
            return False
        except Exception as e:
            self.log_error(f"Erreur inattendue lors de la suppression LDAP: {e}", exc_info=True)
            return False
        finally:
            if conn: conn.unbind_s()

    def change_password(self, user_dn: str,
                        new_password: str,
                        old_password: Optional[str] = None,
                        bind_dn: Optional[str] = None, # DN utilisé pour le bind (peut être user_dn ou admin)
                        bind_password: Optional[str] = None,
                        **conn_kwargs) -> bool:
        """
        Change le mot de passe d'un utilisateur LDAP via l'opération étendue PasswordModify.

        Args:
            user_dn: DN de l'utilisateur dont le mot de passe doit être changé.
            new_password: Nouveau mot de passe en clair.
            old_password: Ancien mot de passe (requis si non admin, dépend du serveur).
            bind_dn: DN pour s'authentifier (si None, utilise user_dn).
            bind_password: Mot de passe pour l'authentification.
            **conn_kwargs: Autres arguments pour la connexion (_connect).

        Returns:
            bool: True si succès.
        """
        if not LDAP_AVAILABLE: return False

        # Utiliser user_dn pour le bind si bind_dn n'est pas fourni
        auth_dn = bind_dn if bind_dn else user_dn
        auth_pass = bind_password # Le mot de passe pour le bind

        if not auth_pass:
             # Essayer de récupérer le mot de passe depuis conn_kwargs s'il y est
             auth_pass = conn_kwargs.get('password')
             if not auth_pass:
                  self.log_error("Mot de passe requis pour l'authentification (bind_password ou password dans conn_kwargs).")
                  return False

        self.log_info(f"Tentative de changement de mot de passe pour: {user_dn}")
        # Passer les kwargs de connexion directement à _connect
        # Assurer que bind_dn et password sont bien ceux pour l'authentification
        final_conn_kwargs = conn_kwargs.copy()
        final_conn_kwargs['bind_dn'] = auth_dn
        final_conn_kwargs['password'] = auth_pass
        conn = self._connect(**final_conn_kwargs)
        if not conn: return False

        try:
            # passwd_s gère l'opération étendue Password Modify (RFC 3062)
            # Les arguments sont: user_dn (cible), old_password, new_password (tous en bytes)
            conn.passwd_s(user_dn,
                          old_password.encode('utf-8') if old_password else None,
                          new_password.encode('utf-8'))
            self.log_success(f"Mot de passe pour {user_dn} changé avec succès.")
            return True
        except INVALID_CREDENTIALS:
             # Peut être soit l'authentification (bind) soit l'ancien mot de passe incorrect
             self.log_error(f"Échec du changement de mot de passe pour {user_dn}: Identifiants invalides (bind ou ancien mot de passe?).")
             return False
        except LDAPError as e:
            self.log_error(f"Erreur LDAP lors du changement de mot de passe pour {user_dn}: {e}")
            # Vérifier les messages d'erreur courants (contraintes de mot de passe, etc.)
            if hasattr(e, 'args') and e.args and isinstance(e.args[0], dict):
                 desc = e.args[0].get('desc', '')
                 info = e.args[0].get('info', '')
                 if 'constraint violation' in desc.lower():
                      self.log_error(f"  Détail: Violation de contrainte (vérifier politique de mot de passe). Info: {info}")
                 else:
                      self.log_error(f"  Description serveur: {desc}, Info: {info}")
            return False
        except Exception as e:
            self.log_error(f"Erreur inattendue lors du changement de mot de passe LDAP: {e}", exc_info=True)
            return False
        finally:
            if conn: conn.unbind_s()

    # --- Fonctions de commodité ---

    def get_user(self, username: str, user_base_dn: str, user_attr: str = 'uid', attributes: Optional[List[str]] = None, **conn_kwargs) -> Optional[Dict[str, Any]]:
        """Recherche un utilisateur par son nom d'utilisateur (ou autre attribut) et retourne ses informations."""
        if not LDAP_AVAILABLE: return None
        # Échapper les caractères spéciaux LDAP dans les valeurs de filtre
        safe_attr = ldap.filter.escape_filter_chars(user_attr)
        safe_username = ldap.filter.escape_filter_chars(username)
        filter_str = f"({safe_attr}={safe_username})"
        # Demander tous les attributs utilisateur si non spécifié
        attrs_to_fetch = attributes # None signifie '*' par défaut dans search_s
        success, results = self.search(base_dn=user_base_dn, scope_str='SUBTREE', filter_str=filter_str, attributes=attrs_to_fetch, **conn_kwargs)
        if success and results:
            if len(results) > 1:
                 self.log_warning(f"Plusieurs utilisateurs trouvés pour {username}, retourne le premier.")
            return results[0]
        self.log_info(f"Utilisateur '{username}' non trouvé dans '{user_base_dn}'.")
        return None

    def check_user_exists(self, username: str, user_base_dn: str, user_attr: str = 'uid', **conn_kwargs) -> bool:
        """Vérifie si un utilisateur existe en cherchant son DN."""
        # Recherche juste le DN, plus rapide
        return self.get_user(username, user_base_dn, user_attr, attributes=['dn'], **conn_kwargs) is not None

    def add_user_to_group(self, user_dn: str, group_dn: str, member_attr: str = 'member', **conn_kwargs) -> bool:
        """Ajoute un utilisateur (par son DN) à un groupe LDAP en modifiant l'attribut membre du groupe."""
        self.log_info(f"Ajout de '{user_dn}' au groupe '{group_dn}' (attribut: {member_attr})")
        # MOD_ADD ajoute la valeur à l'attribut (s'il existe) ou crée l'attribut
        changes = {'add': {member_attr: user_dn}}
        return self.modify(group_dn, changes, **conn_kwargs)

    def remove_user_from_group(self, user_dn: str, group_dn: str, member_attr: str = 'member', **conn_kwargs) -> bool:
        """Supprime un utilisateur (par son DN) d'un groupe LDAP."""
        self.log_info(f"Suppression de '{user_dn}' du groupe '{group_dn}' (attribut: {member_attr})")
        # MOD_DELETE supprime une valeur spécifique d'un attribut
        changes = {'delete': {member_attr: user_dn}}
        # La modification peut échouer si l'utilisateur n'est pas membre (NO_SUCH_ATTRIBUTE),
        # on gère cette exception comme un succès potentiel.
        try:
             success = self.modify(group_dn, changes, **conn_kwargs)
             return success
        except NO_SUCH_ATTRIBUTE:
             self.log_warning(f"L'attribut/valeur à supprimer ('{member_attr}'='{user_dn}') n'existait pas dans '{group_dn}'.")
             return True # Considérer comme succès car l'état final est atteint
        except LDAPError as e:
             # Logguer d'autres erreurs LDAP
             self.log_error(f"Erreur LDAP lors de la suppression de l'utilisateur du groupe: {e}")
             return False

