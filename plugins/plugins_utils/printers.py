#!/usr/bin/env python3
"""
Module utilitaire pour la gestion des imprimantes CUPS.
Permet d'ajouter, supprimer et configurer des imprimantes dans un système Linux.
"""

from .commands import Commands
import os
import json
import re
from typing import Union, Optional, List, Dict, Any, Tuple


class PrinterCommands(Commands):
    """
    Classe pour gérer les imprimantes via CUPS.
    Hérite de la classe Commands pour la gestion des commandes système.
    """
    
    def __init__(self, logger=None, target_ip=None):
        """
        Initialise le gestionnaire d'imprimantes.

        Args:
            logger: Instance de PluginLogger à utiliser
            target_ip: Adresse IP cible pour les logs (optionnel, pour les exécutions SSH)
        """
        super().__init__(logger, target_ip)

    def list_printers(self):
        """
        Liste toutes les imprimantes configurées dans CUPS.

        Returns:
            list: Liste des noms d'imprimantes ou liste vide si erreur
        """
        self.log_debug("Listage des imprimantes configurées")
        success, stdout, _ = self.run(['lpstat', '-p'], no_output=True)

        if not success:
            return []

        printers = []
        for line in stdout.splitlines():
            if line.startswith("printer "):
                # Format: "printer PRINTER_NAME is idle."
                parts = line.split()
                if len(parts) > 1:
                    printers.append(parts[1])

        self.log_debug(f"Imprimantes trouvées: {', '.join(printers) if printers else 'aucune'}")
        return printers

    def remove_all_network_printers(self, exclude_patterns=None):
        """
        Supprime toutes les imprimantes réseau du système.
        Compatible avec les versions françaises de CUPS.

        Args:
            exclude_patterns: Liste de motifs (str) pour exclure certaines imprimantes de la suppression

        Returns:
            tuple: (bool, int, list) - Succès global, nombre d'imprimantes supprimées, et liste des imprimantes supprimées
        """
        self.log_info("Recherche de toutes les imprimantes réseau")

        # Obtenir la liste complète des informations d'imprimantes
        success, stdout, _ = self.run(['lpstat', '-t'], no_output=True, error_as_warning=True)

        if not success:
            self.log_error("Impossible d'obtenir la liste des imprimantes")
            return False, 0, []

        # Motifs pour identifier les imprimantes réseau
        network_patterns = [
            'socket://', 'ipp://', 'http://', 'https://', 'lpd://',
            'ipps://', 'dnssd://', 'AppSocket', 'Internet',
            '192.168.', '10.', '172.', '128.'  # Adresses IP privées courantes
        ]

        # Exclure certaines imprimantes si demandé
        if exclude_patterns is None:
            exclude_patterns = []

        # Rechercher toutes les imprimantes réseau
        network_printers = {}  # Dictionnaire nom -> URI

        for line in stdout.splitlines():
            # Vérifier si la ligne contient un motif d'imprimante réseau
            if any(pattern in line for pattern in network_patterns):
                # Format français : "matériel pour PRINTER_NAME : ipp://IP"
                # Format anglais : "device for PRINTER_NAME: ipp://IP"
                if "matériel pour " in line or "device for " in line:
                    prefix = "matériel pour " if "matériel pour " in line else "device for "
                    parts = line.split(prefix, 1)
                    if len(parts) > 1:
                        uri_parts = parts[1].split(":", 1)
                        if len(uri_parts) > 1:
                            printer_name = uri_parts[0].strip()
                            printer_uri = uri_parts[1].strip()

                            # Vérifier si l'imprimante doit être exclue
                            should_exclude = any(exclude_pattern in printer_name for exclude_pattern in exclude_patterns)

                            if not should_exclude and printer_name != "PDF" and "cups-pdf" not in printer_uri:
                                network_printers[printer_name] = printer_uri

        printer_list = list(network_printers.keys())

        if not printer_list:
            self.log_warning("Aucune imprimante réseau n'a été trouvée")
            return True, 0, []

        # Afficher les imprimantes qui vont être supprimées
        self.log_info(f"Suppression de {len(printer_list)} imprimante(s) réseau: {', '.join(printer_list)}")

        # Afficher les URIs pour le débogage
        for printer, uri in network_printers.items():
            self.log_debug(f"  - {printer}: {uri}")

        # Demander confirmation avant la suppression massive
        if len(printer_list) > 5:
            self.log_warning(f"ATTENTION: Vous êtes sur le point de supprimer {len(printer_list)} imprimantes réseau!")

        # Supprimer toutes les imprimantes réseau
        success_count = 0
        removed_printers = []

        for printer_name in printer_list:
            self.log_info(f"Suppression de l'imprimante réseau: {printer_name}")
            if self.remove_printer(printer_name):
                success_count += 1
                removed_printers.append(printer_name)
            else:
                self.log_error(f"Échec de la suppression de l'imprimante: {printer_name}")

        if success_count == len(printer_list):
            self.log_success(f"Toutes les imprimantes réseau ({success_count}) ont été supprimées avec succès")
            return True, success_count, removed_printers
        else:
            self.log_warning(f"{success_count} sur {len(printer_list)} imprimantes réseau ont été supprimées")
            return success_count > 0, success_count, removed_printers

    def get_default_printer(self):
        """
        Obtient le nom de l'imprimante par défaut.

        Returns:
            str: Nom de l'imprimante par défaut ou None si aucune
        """
        self.log_debug("Recherche de l'imprimante par défaut")
        success, stdout, _ = self.run(['lpstat', '-d'], no_output=True)

        if not success or "no system default destination" in stdout:
            self.log_debug("Aucune imprimante par défaut configurée")
            return None

        # Format: "system default destination: PRINTER_NAME"
        parts = stdout.strip().split(":")
        if len(parts) > 1:
            printer_name = parts[1].strip()
            self.log_debug(f"Imprimante par défaut: {printer_name}")
            return printer_name

        return None

    def add_printer(self, name, ip, driver_param, options=None, ppd=True):
        """
        Ajoute une imprimante au système CUPS avec une interface simplifiée.

        Args:
            name: Nom de l'imprimante
            ip: Adresse IP ou URI de l'imprimante
                (ex: "192.168.1.100" ou "socket://192.168.1.100:9100")
            driver_param: Chemin vers le fichier PPD ou nom du pilote
            options: Dictionnaire d'options ou chaîne d'options pour l'imprimante
            ppd: Si True, driver_param est un fichier PPD, sinon c'est un nom de pilote

        Returns:
            bool: True si l'ajout a réussi, False sinon
        """
        # Vérifier et formater l'URI de l'imprimante
        if "://" not in ip:
            # Pas d'URI spécifiée, supposer socket://
            printer_uri = f"socket://{ip}"
            if ":" not in ip:
                # Ajouter le port par défaut
                printer_uri += ":9100"
        else:
            # URI déjà spécifiée
            printer_uri = ip

        # Convertir les options si elles sont fournies sous forme de chaîne
        printer_options = {}

        if options:
            if isinstance(options, dict):
                printer_options = options
            elif isinstance(options, str):
                # Parser les options au format "-o Option1=Value1 -o Option2=Value2"
                for opt in options.split("-o"):
                    opt = opt.strip()
                    if opt and "=" in opt:
                        key, value = opt.split("=", 1)
                        printer_options[key.strip()] = value.strip()

        # Ajouter des options par défaut si non spécifiées
        if "printer-is-shared" not in printer_options:
            printer_options["printer-is-shared"] = "false"

        # Construire la commande avec les paramètres de base
        cmd = ["lpadmin", "-p", name, "-v", printer_uri, "-u", "allow:all", "-E"]

        # Ajouter le pilote ou le fichier PPD
        if ppd:
            cmd.extend(["-P", driver_param])
            driver_info = f"PPD {driver_param}"
        else:
            cmd.extend(["-m", driver_param])
            driver_info = f"pilote {driver_param}"

        # Ajouter les options supplémentaires
        for key, value in printer_options.items():
            cmd.extend(["-o", f"{key}={value}"])

        self.log_info(f"Ajout de l'imprimante {name} ({printer_uri}) avec {driver_info}")
        success, stdout, stderr = self.run(cmd, print_command=True)

        if success:
            self.log_success(f"Imprimante {name} ajoutée avec succès")
        else:
            self.log_error(f"Échec de l'ajout de l'imprimante {name}")
            if stderr:
                self.log_error(f"Erreur: {stderr}")

        return success

    def remove_printer(self, printer_name):
        """
        Supprime une imprimante du système CUPS.

        Args:
            printer_name: Nom de l'imprimante à supprimer

        Returns:
            bool: True si la suppression a réussi, False sinon
        """
        self.log_info(f"Suppression de l'imprimante {printer_name}")
        success, _, _ = self.run(['lpadmin', '-x', printer_name])

        if success:
            self.log_success(f"Imprimante {printer_name} supprimée avec succès")
        else:
            self.log_error(f"Échec de la suppression de l'imprimante {printer_name}")

        return success

    def remove_printer_by_ip(self, ip_address):
        """
        Supprime toutes les imprimantes associées à une adresse IP.
        Compatible avec les versions françaises de CUPS.

        Args:
            ip_address: Adresse IP de l'imprimante à supprimer

        Returns:
            tuple: (bool, int) - Succès global et nombre d'imprimantes supprimées
        """
        self.log_info(f"Recherche des imprimantes associées à l'IP {ip_address}")

        # Obtenir la liste complète des informations d'imprimantes
        success, stdout, _ = self.run(['lpstat', '-t'], no_output=True, error_as_warning=True)

        if not success:
            self.log_error(f"Impossible d'obtenir la liste des imprimantes")
            return False, 0

        # Stocker les lignes pour le débogage
        self.log_debug(f"Sortie complète de lpstat -t:")
        for line in stdout.splitlines():
            self.log_debug(f"  {line}")

        # Rechercher les imprimantes associées à l'IP
        printers_to_remove = []

        for line in stdout.splitlines():
            if ip_address in line:
                # La ligne contient l'IP, essayons d'extraire le nom de l'imprimante
                if "matériel pour " in line or "device for " in line:
                    # Format français : "matériel pour PRINTER_NAME : ipp://IP"
                    # Format anglais : "device for PRINTER_NAME: ipp://IP"
                    prefix = "matériel pour " if "matériel pour " in line else "device for "
                    name_part = line.split(prefix, 1)[1].split(":", 1)[0].strip()
                    if name_part and name_part not in printers_to_remove:
                        printers_to_remove.append(name_part)

        if not printers_to_remove:
            self.log_warning(f"Aucune imprimante associée à l'IP {ip_address} n'a été trouvée")
            return True, 0

        self.log_info(f"Imprimantes trouvées: {printers_to_remove}")

        # Supprimer toutes les imprimantes trouvées
        self.log_info(f"Suppression de {len(printers_to_remove)} imprimante(s) associée(s) à l'IP {ip_address}: {', '.join(printers_to_remove)}")

        success_count = 0
        for printer in printers_to_remove:
            self.log_info(f"Suppression de l'imprimante: {printer}")
            if self.remove_printer(printer):
                success_count += 1

        if success_count == len(printers_to_remove):
            self.log_success(f"Toutes les imprimantes associées à l'IP {ip_address} ont été supprimées avec succès")
            return True, success_count
        else:
            self.log_warning(f"{success_count} sur {len(printers_to_remove)} imprimantes ont été supprimées avec succès")
            return success_count > 0, success_count


    def remove_printers_by_pattern(self, pattern):
        """
        Supprime toutes les imprimantes dont le nom correspond à un motif.

        Args:
            pattern: Expression régulière pour filtrer les noms d'imprimantes

        Returns:
            tuple: (bool, int) - Succès global et nombre d'imprimantes supprimées
        """
        self.log_info(f"Recherche des imprimantes correspondant au motif '{pattern}'")

        # Obtenir la liste des imprimantes
        printers = self.list_printers()

        if not printers:
            self.log_warning("Aucune imprimante n'est configurée sur le système")
            return True, 0

        # Filtrer les imprimantes correspondant au motif
        printers_to_remove = []
        try:
            regex = re.compile(pattern)
            for printer in printers:
                if regex.search(printer):
                    printers_to_remove.append(printer)
        except re.error:
            # Si l'expression régulière est invalide, utiliser une correspondance simple
            self.log_warning(f"Expression régulière invalide '{pattern}', utilisation d'une correspondance simple")
            for printer in printers:
                if pattern in printer:
                    printers_to_remove.append(printer)

        if not printers_to_remove:
            self.log_warning(f"Aucune imprimante ne correspond au motif '{pattern}'")
            return True, 0

        # Supprimer toutes les imprimantes correspondantes
        self.log_info(f"Suppression de {len(printers_to_remove)} imprimante(s) correspondant au motif '{pattern}': {', '.join(printers_to_remove)}")

        success_count = 0
        for printer in printers_to_remove:
            if self.remove_printer(printer):
                success_count += 1

        if success_count == len(printers_to_remove):
            self.log_success(f"Toutes les imprimantes correspondant au motif '{pattern}' ont été supprimées avec succès")
            return True, success_count
        else:
            self.log_warning(f"{success_count} sur {len(printers_to_remove)} imprimantes ont été supprimées avec succès")
            return success_count > 0, success_count

    def get_printer_uri(self, printer_name):
        """
        Obtient l'URI d'une imprimante.

        Args:
            printer_name: Nom de l'imprimante

        Returns:
            str: URI de l'imprimante ou None si non trouvée
        """
        self.log_debug(f"Récupération de l'URI de l'imprimante {printer_name}")
        success, stdout, _ = self.run(['lpstat', '-v', printer_name], no_output=True)

        if not success:
            self.log_error(f"Imprimante {printer_name} non trouvée")
            return None

        # Format: "device for PRINTER_NAME: socket://192.168.1.100:9100"
        for line in stdout.splitlines():
            if f"device for {printer_name}:" in line:
                uri = line.split(":", 1)[1].strip()
                self.log_debug(f"URI de l'imprimante {printer_name}: {uri}")
                return uri

        return None

    def get_printers_by_ip(self, ip_address):
        """
        Obtient la liste des imprimantes associées à une adresse IP.
        Compatible avec les versions françaises de CUPS.

        Args:
            ip_address: Adresse IP à rechercher

        Returns:
            list: Liste des noms d'imprimantes associées à cette IP
        """
        self.log_debug(f"Recherche des imprimantes associées à l'IP {ip_address}")

        # Obtenir la liste complète des informations d'imprimantes
        success, stdout, _ = self.run(['lpstat', '-t'], no_output=True)

        if not success:
            self.log_error(f"Impossible d'obtenir la liste des imprimantes")
            return []

        # Rechercher les imprimantes associées à l'IP
        printers = []

        for line in stdout.splitlines():
            if ip_address in line:
                # La ligne contient l'IP, essayons d'extraire le nom de l'imprimante
                if "matériel pour " in line or "device for " in line:
                    # Format français : "matériel pour PRINTER_NAME : ipp://IP"
                    # Format anglais : "device for PRINTER_NAME: ipp://IP"
                    prefix = "matériel pour " if "matériel pour " in line else "device for "
                    name_part = line.split(prefix, 1)[1].split(":", 1)[0].strip()
                    if name_part and name_part not in printers:
                        printers.append(name_part)

        self.log_debug(f"Imprimantes associées à l'IP {ip_address}: {', '.join(printers) if printers else 'aucune'}")
        return printers

    def set_default_printer(self, printer_name):
        """
        Définit une imprimante comme imprimante par défaut.

        Args:
            printer_name: Nom de l'imprimante à définir par défaut

        Returns:
            bool: True si l'opération a réussi, False sinon
        """
        self.log_info(f"Définition de {printer_name} comme imprimante par défaut")
        success, _, _ = self.run(['lpadmin', '-d', printer_name])

        if success:
            self.log_success(f"Imprimante {printer_name} définie comme imprimante par défaut")
        else:
            self.log_error(f"Échec de la définition de {printer_name} comme imprimante par défaut")

        return success

    def enable_printer(self, printer_name):
        """
        Active une imprimante.

        Args:
            printer_name: Nom de l'imprimante à activer

        Returns:
            bool: True si l'activation a réussi, False sinon
        """
        self.log_info(f"Activation de l'imprimante {printer_name}")
        success, _, _ = self.run(['cupsenable', printer_name])

        if success:
            self.log_success(f"Imprimante {printer_name} activée avec succès")
        else:
            self.log_error(f"Échec de l'activation de l'imprimante {printer_name}")

        return success

    def disable_printer(self, printer_name):
        """
        Désactive une imprimante.

        Args:
            printer_name: Nom de l'imprimante à désactiver

        Returns:
            bool: True si la désactivation a réussi, False sinon
        """
        self.log_info(f"Désactivation de l'imprimante {printer_name}")
        success, _, _ = self.run(['cupsdisable', printer_name])

        if success:
            self.log_success(f"Imprimante {printer_name} désactivée avec succès")
        else:
            self.log_error(f"Échec de la désactivation de l'imprimante {printer_name}")

        return success

    def get_printer_options(self, printer_name):
        """
        Obtient les options d'une imprimante.

        Args:
            printer_name: Nom de l'imprimante

        Returns:
            dict: Dictionnaire des options de l'imprimante ou None si erreur
        """
        self.log_debug(f"Récupération des options de l'imprimante {printer_name}")
        success, stdout, _ = self.run(['lpoptions', '-p', printer_name, '-l'], no_output=True)

        if not success:
            self.log_error(f"Impossible de récupérer les options de {printer_name}")
            return None

        options = {}
        for line in stdout.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                options[key.strip()] = value.strip()

        return options

    def set_printer_option(self, printer_name, option, value):
        """
        Définit une option pour une imprimante.

        Args:
            printer_name: Nom de l'imprimante
            option: Nom de l'option
            value: Valeur de l'option

        Returns:
            bool: True si l'opération a réussi, False sinon
        """
        self.log_info(f"Configuration de l'option {option}={value} pour {printer_name}")
        success, _, _ = self.run(['lpadmin', '-p', printer_name, '-o', f"{option}={value}"])

        if success:
            self.log_success(f"Option {option} configurée pour {printer_name}")
        else:
            self.log_error(f"Échec de la configuration de l'option {option} pour {printer_name}")

        return success

    def restart_cups(self):
        """
        Redémarre le service CUPS.

        Returns:
            bool: True si le redémarrage a réussi, False sinon
        """
        self.log_info("Redémarrage du service CUPS")
        success, _, _ = self.run_as_root(['systemctl', 'restart', 'cups'])

        if success:
            self.log_success("Service CUPS redémarré avec succès")
        else:
            self.log_error("Échec du redémarrage du service CUPS")

        return success

    def get_printer_status(self, printer_name):
        """
        Obtient l'état d'une imprimante.

        Args:
            printer_name: Nom de l'imprimante

        Returns:
            str: État de l'imprimante ou None si erreur
        """
        self.log_debug(f"Vérification de l'état de l'imprimante {printer_name}")
        success, stdout, _ = self.run(['lpstat', '-p', printer_name], no_output=True)

        if not success:
            self.log_error(f"Impossible d'obtenir l'état de {printer_name}")
            return None

        for line in stdout.splitlines():
            if printer_name in line:
                # Format: "printer PRINTER_NAME is idle." ou "printer PRINTER_NAME is stopped."
                status = line.split("is", 1)[1].strip().rstrip(".")
                self.log_debug(f"État de {printer_name}: {status}")
                return status

        return None