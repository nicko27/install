# install/plugins/plugins_utils/printers.py
#!/usr/bin/env python3
"""
Module utilitaire pour la gestion des imprimantes CUPS.
Permet d'ajouter, supprimer et configurer des imprimantes dans un système Linux.
"""

from plugins_utils.plugins_utils_base import PluginsUtilsBase # Hériter de la nouvelle base
import os
import re
import time
from typing import Union, Optional, List, Dict, Any, Tuple

class PrinterCommands(PluginsUtilsBase):
    """
    Classe pour gérer les imprimantes via CUPS (lpadmin, lpstat, etc.).
    Hérite de PluginUtilsBase pour l'exécution de commandes et la progression.
    """

    def __init__(self, logger=None, target_ip=None):
        super().__init__(logger, target_ip)

    def list_printers(self, log_levels: Optional[Dict[str, str]] = None) -> List[str]:
        """
        Liste toutes les imprimantes configurées dans CUPS.

        Returns:
            Liste des noms d'imprimantes ou liste vide si erreur.
        """
        self.log_debug("Listage des imprimantes configurées (lpstat -p)", log_levels=log_levels)
        # Utiliser check=False car lpstat peut retourner 1 si aucune imprimante n'est trouvée
        success, stdout, stderr = self.run(['lpstat', '-p'], check=False, no_output=True, error_as_warning=True, needs_sudo=False)

        printers = []
        if success or "no printers found" in stderr.lower(): # Gérer le cas où aucune imprimante n'est une "erreur" pour lpstat
            for line in stdout.splitlines():
                # Format: "printer PRINTER_NAME is idle." (ou autre statut)
                # Format FR: "imprimante PRINTER_NAME est inactive."
                if line.startswith("printer ") or line.startswith("imprimante "):
                    parts = line.split()
                    if len(parts) > 1:
                        printers.append(parts[1])
            self.log_debug(f"Imprimantes trouvées: {', '.join(printers) if printers else 'aucune'}", log_levels=log_levels)
        else:
             self.log_error(f"Impossible d'obtenir la liste des imprimantes. Stderr: {stderr}", log_levels=log_levels)

        return printers

    def get_printer_details(self, printer_name: Optional[str] = None, log_levels: Optional[Dict[str, str]] = None) -> Dict[str, Dict[str, str]]:
        """
        Récupère les détails (URI, statut, etc.) d'une ou toutes les imprimantes.

        Args:
            printer_name: Nom de l'imprimante (optionnel, toutes si None).

        Returns:
            Dictionnaire des détails {nom_imprimante: {uri: ..., status: ...}}.
        """
        self.log_debug(f"Récupération des détails pour {'toutes les imprimantes' if printer_name is None else printer_name} (lpstat -t)", log_levels=log_levels)
        # lpstat -t donne toutes les infos, y compris URI et statut
        # check=False car peut retourner 1 si aucune imprimante
        success, stdout, stderr = self.run(['lpstat', '-t'], check=False, no_output=True, error_as_warning=True, needs_sudo=False)

        details = {}
        if not success and "no printers found" not in stderr.lower():
            self.log_error(f"Impossible d'obtenir les détails des imprimantes. Stderr: {stderr}", log_levels=log_levels)
            return details

        # Dictionnaire temporaire pour stocker les informations URI avant de les associer aux statuts
        printer_uris = {}
        printer_info_dict = {}

        # 1. D'abord, récupérer toutes les URI des imprimantes
        for line in stdout.splitlines():
            # Format: "matériel pour PRINTER_NAME : uri"
            if "matériel pour " in line and ":" in line:
                try:
                    # Extraire le nom de l'imprimante et l'URI
                    parts = line.split("matériel pour ")[1].split(":", 1)
                    printer_name_from_line = parts[0].strip()
                    uri = parts[1].strip()
                    printer_uris[printer_name_from_line] = uri
                    self.log_debug(f"URI pour {printer_name_from_line}: {uri}", log_levels=log_levels)
                except (IndexError, KeyError) as e:
                    self.log_warning(f"Impossible d'extraire l'URI de la ligne: {line}. Erreur: {e}", log_levels=log_levels)
        
        # 2. Ensuite, récupérer les statuts des imprimantes
        for line in stdout.splitlines():
            # Format: "printer PRINTER_NAME is idle.  enabled since..."
            if line.startswith("printer "):
                try:
                    parts = line.split(" is ", 1)  # Diviser sur "is" pour séparer le nom et le statut
                    if len(parts) == 2:
                        # Extraire le nom (après "printer ")
                        printer_name_from_line = parts[0].replace("printer ", "").strip()
                        # Extraire le statut
                        status = parts[1].strip()
                        
                        # Créer ou mettre à jour les informations de l'imprimante
                        if printer_name_from_line not in printer_info_dict:
                            printer_info_dict[printer_name_from_line] = {'name': printer_name_from_line, 'status': status}
                        else:
                            printer_info_dict[printer_name_from_line]['status'] = status
                        
                        # Ajouter l'URI si disponible
                        if printer_name_from_line in printer_uris:
                            printer_info_dict[printer_name_from_line]['uri'] = printer_uris[printer_name_from_line]
                        
                        self.log_debug(f"Statut pour {printer_name_from_line}: {status}", log_levels=log_levels)
                except Exception as e:
                    self.log_warning(f"Impossible d'extraire le statut de la ligne: {line}. Erreur: {e}", log_levels=log_levels)

        # Finaliser le dictionnaire des détails
        details = printer_info_dict

        # Filtrer si un nom spécifique est demandé
        if printer_name:
            return {printer_name: details[printer_name]} if printer_name in details else {}

        self.log_debug(f"Détails récupérés pour {len(details)} imprimantes.", log_levels=log_levels)
        return details

    def remove_all_network_printers(self, exclude_patterns: Optional[List[str]] = None, task_id: Optional[str] = None, log_levels: Optional[Dict[str, str]] = None) -> Tuple[bool, int, List[str]]:
        """
        Supprime toutes les imprimantes réseau du système.

        Args:
            exclude_patterns: Liste de motifs (str) pour exclure certaines imprimantes.
            task_id: ID de tâche pour la progression (optionnel).

        Returns:
            Tuple (succès_global: bool, nb_supprimées: int, liste_supprimées: List[str]).
        """
        self.log_info("Recherche de toutes les imprimantes réseau à supprimer", log_levels=log_levels)
        exclude_set = set(exclude_patterns or [])

        # 1. Obtenir les détails de toutes les imprimantes
        all_details = self.get_printer_details()
        if not all_details:
            self.log_info("Aucune imprimante trouvée sur le système.", log_levels=log_levels)
            return True, 0, []

        # 2. Identifier les imprimantes réseau à supprimer
        network_printers_to_remove = []
        network_patterns = ['socket://', 'ipp://', 'http://', 'https://', 'lpd://', 'ipps://', 'dnssd://', 'AppSocket']
        ip_pattern = re.compile(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}') # Regex simple pour IP v4

        for name, info in all_details.items():
            uri = info.get('uri', '').lower()
            is_network = any(proto in uri for proto in network_patterns) or bool(ip_pattern.search(uri))
            is_excluded = any(re.search(pattern, name) for pattern in exclude_set) # Utiliser regex pour les patterns

            if is_network and not is_excluded and name != "PDF" and "cups-pdf" not in uri:
                network_printers_to_remove.append(name)

        if not network_printers_to_remove:
            self.log_info("Aucune imprimante réseau à supprimer trouvée.", log_levels=log_levels)
            return True, 0, []

        # 3. Supprimer les imprimantes identifiées
        count = len(network_printers_to_remove)
        self.log_info(f"Suppression de {count} imprimante(s) réseau: {', '.join(network_printers_to_remove)}", log_levels=log_levels)
        current_task_id = task_id or f"remove_printers_{int(time.time())}"
        self.start_task(count, description="Suppression imprimantes réseau", task_id=current_task_id)

        success_count = 0
        removed_list = []
        all_success = True

        for name in network_printers_to_remove:
            if self.remove_printer(name):
                success_count += 1
                removed_list.append(name)
            else:
                all_success = False # Marquer l'échec global si une suppression échoue
            self.update_task(description=f"Suppression {name}")

        final_message = f"{success_count}/{count} imprimantes réseau supprimées."
        self.complete_task(success=all_success, message=final_message)

        if not all_success:
             self.log_warning(final_message, log_levels=log_levels)
        else:
             self.log_success(final_message, log_levels=log_levels)

        return all_success, success_count, removed_list

    def remove_printer_by_ip(self, ip_address: str, task_id: Optional[str] = None, log_levels: Optional[Dict[str, str]] = None) -> Tuple[bool, int]:
        """
        Supprime toutes les imprimantes associées à une adresse IP.

        Args:
            ip_address: Adresse IP de l'imprimante à supprimer.
            task_id: ID de tâche pour la progression (optionnel).

        Returns:
            Tuple (succès_global: bool, nb_supprimées: int).
        """
        self.log_info(f"Recherche des imprimantes associées à l'IP {ip_address}", log_levels=log_levels)

        # 1. Obtenir les détails de toutes les imprimantes
        all_details = self.get_printer_details()
        if not all_details:
            self.log_info("Aucune imprimante trouvée sur le système.", log_levels=log_levels)
            return True, 0

        # 2. Identifier les imprimantes avec cette IP
        printers_to_remove = [name for name, info in all_details.items() if ip_address in info.get('uri', '')]

        if not printers_to_remove:
            self.log_info(f"Aucune imprimante trouvée pour l'IP {ip_address}.", log_levels=log_levels)
            return True, 0

        # 3. Supprimer les imprimantes
        count = len(printers_to_remove)
        self.log_info(f"Suppression de {count} imprimante(s) pour l'IP {ip_address}: {', '.join(printers_to_remove)}", log_levels=log_levels)
        current_task_id = task_id or f"remove_ip_{ip_address.replace('.', '_')}_{int(time.time())}"
        self.start_task(count, description=f"Suppression imprimantes IP {ip_address}", task_id=current_task_id)

        success_count = 0
        all_success = True
        for name in printers_to_remove:
            if self.remove_printer(name):
                success_count += 1
            else:
                all_success = False
            self.update_task(description=f"Suppression {name}")

        final_message = f"{success_count}/{count} imprimantes supprimées pour l'IP {ip_address}."
        self.complete_task(success=all_success, message=final_message)

        if not all_success:
             self.log_warning(final_message, log_levels=log_levels)
        else:
             self.log_success(final_message, log_levels=log_levels)

        return all_success, success_count

    def add_printer(self,
                    name: str,
                    uri: str,
                    ppd_file: Optional[str] = None,
                    model: Optional[str] = None,
                    options: Optional[Dict[str, str]] = None,
                    make_default: bool = False,
                    shared: bool = False,
enabled: bool = True, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """
        Ajoute une imprimante au système CUPS avec plus de contrôle.

        Args:
            name: Nom de l'imprimante (doit être unique).
            uri: URI du périphérique (ex: socket://..., ipp://..., /dev/usb/lp0).
            ppd_file: Chemin absolu vers le fichier PPD (prioritaire sur model).
            model: Nom du modèle pour utiliser un pilote générique ou système (ex: drv:///...).
            options: Dictionnaire d'options CUPS {option: valeur}.
            make_default: Si True, définit cette imprimante par défaut.
            shared: Si True, partage l'imprimante sur le réseau.
            enabled: Si True (défaut), active l'imprimante après ajout.

        Returns:
            bool: True si l'ajout a réussi.
        """
        self.log_debug(f"Tentative d'ajout de l'imprimante: {name} (URI: {uri})", log_levels=log_levels)

        if not name or not uri:
             self.log_error("Le nom et l'URI de l'imprimante sont requis.", log_levels=log_levels)
             return False
        if not ppd_file and not model:
             self.log_error("Un fichier PPD ou un nom de modèle doit être fourni.", log_levels=log_levels)
             return False
        if ppd_file and not os.path.isabs(ppd_file):
             self.log_error(f"Le chemin PPD doit être absolu: {ppd_file}", log_levels=log_levels)
             # Alternative: essayer de le résoudre relativement à un dossier PPD standard?
             return False
        if ppd_file and not os.path.exists(ppd_file):
             self.log_error(f"Le fichier PPD n'existe pas: {ppd_file}", log_levels=log_levels)
             return False

        cmd = ['lpadmin', '-p', name, '-v', uri]

        # Ajouter le pilote
        if ppd_file:
             cmd.extend(['-P', ppd_file])
             self.log_debug(f"Utilisation du fichier PPD: {ppd_file}", log_levels=log_levels)
        else: # model doit être défini
             cmd.extend(['-m', model])
             self.log_debug(f"Utilisation du modèle/pilote: {model}", log_levels=log_levels)

        # Activer/Désactiver l'imprimante
        cmd.append('-E' if enabled else '-D') # -E active, -D désactive (ancienne syntaxe?)
        # Note: Il est souvent préférable d'activer après avec cupsenable

        # Options par défaut et fournies
        final_options = {"printer-is-shared": "true" if shared else "false"}
        if options:
            final_options.update(options)

        for key, value in final_options.items():
            cmd.extend(['-o', f"{key}={value}"])
        self.log_debug(f"Options appliquées: {final_options}", log_levels=log_levels)

        # Exécuter la commande
        success, stdout, stderr = self.run(cmd, check=False, error_as_warning=True, needs_sudo=False)

        if not success:
            self.log_error(f"Échec de l'ajout de l'imprimante {name}.", log_levels=log_levels)
            if "client-error-bad-request" in stderr and ppd_file:
                 self.log_error("Cela peut indiquer un problème avec le fichier PPD.", log_levels=log_levels)
            elif "client-error-not-found" in stderr:
                 self.log_error("Vérifier que l'URI ou le modèle/PPD est correct.", log_levels=log_levels)
            self.log_error(f"Stderr: {stderr}", log_levels=log_levels)
            return False

        self.log_success(f"Imprimante {name} ajoutée avec succès via lpadmin.", log_levels=log_levels)

        # Activer explicitement si demandé (plus fiable que -E)
        if enabled:
            enable_success = self.enable_printer(name)
            if not enable_success:
                 self.log_warning(f"L'imprimante {name} a été ajoutée mais n'a pas pu être activée.", log_levels=log_levels)
                 # Continuer quand même, l'ajout principal a réussi

        # Définir par défaut si demandé
        if make_default:
            default_success = self.set_default_printer(name)
            if not default_success:
                 self.log_warning(f"L'imprimante {name} a été ajoutée mais n'a pas pu être définie par défaut.", log_levels=log_levels)
                 # Continuer quand même

        return True # L'ajout principal a réussi

    def remove_printer(self, printer_name: str, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """
        Supprime une imprimante du système CUPS.

        Args:
            printer_name: Nom de l'imprimante à supprimer.

        Returns:
            bool: True si la suppression a réussi.
        """
        self.log_info(f"Suppression de l'imprimante: {printer_name}", log_levels=log_levels)
        # Utiliser check=False pour gérer le cas où l'imprimante n'existe pas déjà
        success, stdout, stderr = self.run(['lpadmin', '-x', printer_name], check=False, error_as_warning=False, needs_sudo=False)

        if success:
             self.log_success(f"Imprimante {printer_name} supprimée avec succès.", log_levels=log_levels)
             return True
        else:
             # Vérifier si l'erreur est due au fait que l'imprimante n'existe pas
             if "client-error-not-found" in stderr.lower() or "unknown printer" in stderr.lower():
                  self.log_warning(f"L'imprimante {printer_name} n'existait déjà pas.", log_levels=log_levels)
                  return True # Considérer comme un succès si elle n'existe pas
             else:
                  self.log_error(f"Échec de la suppression de l'imprimante {printer_name}. Stderr: {stderr}", log_levels=log_levels)
                  return False

    def get_default_printer(self, log_levels: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Obtient le nom de l'imprimante par défaut."""
        self.log_debug("Recherche de l'imprimante par défaut (lpstat -d)", log_levels=log_levels)
        success, stdout, stderr = self.run(['lpstat', '-d'], check=False, no_output=True, error_as_warning=False, needs_sudo=False)

        if not success or "no system default destination" in stdout.lower() or "aucun système destinataire par défaut" in stdout.lower():
            self.log_info("Aucune imprimante par défaut configurée.", log_levels=log_levels)
            return None

        # Format EN: "system default destination: PRINTER_NAME"
        # Format FR: "système destinataire par défaut : PRINTER_NAME"
        match = re.search(r':\s*(\S+)', stdout.strip())
        if match:
            printer_name = match.group(1)
            self.log_info(f"Imprimante par défaut: {printer_name}", log_levels=log_levels)
            return printer_name

        self.log_warning(f"Impossible d'extraire l'imprimante par défaut de la sortie: {stdout}", log_levels=log_levels)
        return None

    def set_default_printer(self, printer_name: str, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """Définit une imprimante comme imprimante par défaut."""
        self.log_info(f"Définition de '{printer_name}' comme imprimante par défaut", log_levels=log_levels)
        success, _, stderr = self.run(['lpadmin', '-d', printer_name], check=False, error_as_warning=False, needs_sudo=False)
        if success:
             self.log_success(f"Imprimante '{printer_name}' définie par défaut.", log_levels=log_levels)
             return True
        else:
             self.log_error(f"Échec de la définition de '{printer_name}' par défaut. Stderr: {stderr}", log_levels=log_levels)
             return False

    def enable_printer(self, printer_name: str, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """Active une imprimante (accepte les travaux)."""
        self.log_debug(f"Activation de l'imprimante: {printer_name}", log_levels=log_levels)
        success, _, stderr = self.run(['cupsenable', printer_name], check=False, error_as_warning=False, needs_sudo=False)
        if success:
             self.log_success(f"Imprimante {printer_name} activée.", log_levels=log_levels)
             return True
        else:
             # Gérer le cas où elle est déjà activée
             if "already enabled" in stderr.lower():
                  self.log_info(f"Imprimante {printer_name} déjà activée.", log_levels=log_levels)
                  return True
             self.log_error(f"Échec de l'activation de {printer_name}. Stderr: {stderr}", log_levels=log_levels)
             return False

    def disable_printer(self, printer_name: str, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """Désactive une imprimante (rejette les travaux)."""
        self.log_info(f"Désactivation de l'imprimante: {printer_name}", log_levels=log_levels)
        success, _, stderr = self.run(['cupsdisable', printer_name], check=False)
        if success:
             self.log_success(f"Imprimante {printer_name} désactivée.", log_levels=log_levels)
             return True
        else:
             # Gérer le cas où elle est déjà désactivée
             if "already stopped" in stderr.lower(): # cupsdisable peut dire 'stopped'
                  self.log_info(f"Imprimante {printer_name} déjà désactivée.", log_levels=log_levels)
                  return True
             self.log_error(f"Échec de la désactivation de {printer_name}. Stderr: {stderr}", log_levels=log_levels)
             return False

    def get_printer_options(self, printer_name: str, log_levels: Optional[Dict[str, str]] = None) -> Optional[Dict[str, str]]:
        """Obtient les options configurées pour une imprimante."""
        self.log_debug(f"Récupération des options pour {printer_name} (lpoptions -p ... -l)", log_levels=log_levels)
        cmd = ['lpoptions', '-p', printer_name, '-l']
        success, stdout, stderr = self.run(cmd, check=False, no_output=True)

        if not success:
            self.log_error(f"Impossible de récupérer les options de {printer_name}. Stderr: {stderr}", log_levels=log_levels)
            return None

        options = {}
        # Format: OptionName/Option Label: Value1 *Value2 Value3
        for line in stdout.splitlines():
            if ":" in line:
                key_part, value_part = line.split(":", 1)
                key = key_part.split('/')[0].strip() # Prend la partie avant le /
                # La valeur par défaut est marquée par '*'
                default_value = None
                values = []
                for val in value_part.split():
                    if val.startswith('*'):
                        default_value = val[1:]
                        values.append(default_value)
                    else:
                        values.append(val)
                # Stocker la valeur par défaut ou la première si pas de défaut
                options[key] = default_value if default_value is not None else (values[0] if values else '')
        self.log_debug(f"Options trouvées pour {printer_name}: {options}", log_levels=log_levels)
        return options

    def set_printer_option(self, printer_name: str, option: str, value: str, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """Définit une option pour une imprimante."""
        self.log_info(f"Configuration de l'option {option}={value} pour {printer_name}", log_levels=log_levels)
        cmd = ['lpoptions', '-p', printer_name, '-o', f"{option}={value}"]
        success, _, stderr = self.run(cmd, check=False)
        if success:
             self.log_success(f"Option {option} configurée pour {printer_name}.", log_levels=log_levels)
             return True
        else:
             self.log_error(f"Échec de la configuration de l'option {option}. Stderr: {stderr}", log_levels=log_levels)
             return False

    def restart_cups(self, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """Redémarre le service CUPS."""
        self.log_info("Redémarrage du service CUPS", log_levels=log_levels)
        # Utiliser la classe ServiceCommands si disponible, sinon appel direct
        try:
            from .services import ServiceCommands
            service_manager = ServiceCommands(self.logger, self.target_ip)
            return service_manager.restart("cups")
        except ImportError:
             self.log_warning("Module ServiceCommands non trouvé, utilisation de systemctl directement.", log_levels=log_levels)
             success, _, stderr = self.run(['systemctl', 'restart', 'cups'], check=False)
             if success:
                  self.log_success("Service CUPS redémarré avec succès.", log_levels=log_levels)
             else:
                  self.log_error(f"Échec du redémarrage du service CUPS. Stderr: {stderr}", log_levels=log_levels)
             return success

    def get_printer_status(self, printer_name: str, log_levels: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Obtient l'état actuel d'une imprimante."""
        details = self.get_printer_details(printer_name)
        if printer_name in details:
            status = details[printer_name].get('status', 'inconnu')
            self.log_debug(f"État de {printer_name}: {status}", log_levels=log_levels)
            return status
        else:
             self.log_warning(f"Impossible d'obtenir le statut de l'imprimante {printer_name} (non trouvée).", log_levels=log_levels)
             return None