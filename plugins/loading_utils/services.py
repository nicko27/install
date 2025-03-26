#!/usr/bin/env python3
"""
Module utilitaire pour la gestion des services systemd.
Permet de démarrer, arrêter, redémarrer et vérifier l'état des services du système.
"""

from .commands import Commands


class ServiceCommands(Commands):
    """
    Classe pour gérer les services systemd.
    Hérite de la classe Commands pour la gestion des commandes système.
    
    Les méthodes acceptent un paramètre optionnel root_credentials qui permet de spécifier
    les informations d'identification pour sudo. Format: {'user': 'username', 'password': 'password'}
    """

    def start(self, service_name):
        """
        Démarre un service systemd.

        Args:
            service_name: Nom du service à démarrer
            root_credentials: Dictionnaire contenant les informations d'identification root (optionnel)
                             Format: {'user': 'root_username', 'password': 'root_password'}

        Returns:
            bool: True si le démarrage a réussi, False sinon
        """
        self.log_info(f"Démarrage du service {service_name}")
        success, _, _ = self.run(['systemctl', 'start', service_name])

        if success:
            self.log_success(f"Service {service_name} démarré avec succès")
        else:
            self.log_error(f"Échec du démarrage du service {service_name}")

        return success

    def stop(self, service_name):
        """
        Arrête un service systemd.

        Args:
            service_name: Nom du service à arrêter
            root_credentials: Dictionnaire contenant les informations d'identification root (optionnel)
                             Format: {'user': 'root_username', 'password': 'root_password'}

        Returns:
            bool: True si l'arrêt a réussi, False sinon
        """
        self.log_info(f"Arrêt du service {service_name}")
        success, _, _ = self.run(['systemctl', 'stop', service_name])

        if success:
            self.log_success(f"Service {service_name} arrêté avec succès")
        else:
            self.log_error(f"Échec de l'arrêt du service {service_name}")

        return success

    def restart(self, service_name):
        """
        Redémarre un service systemd.

        Args:
            service_name: Nom du service à redémarrer
            root_credentials: Dictionnaire contenant les informations d'identification root (optionnel)
                             Format: {'user': 'root_username', 'password': 'root_password'}

        Returns:
            bool: True si le redémarrage a réussi, False sinon
        """
        self.log_info(f"Redémarrage du service {service_name}")
        success, _, _ = self.run(['systemctl', 'restart', service_name])

        if success:
            self.log_success(f"Service {service_name} redémarré avec succès")
        else:
            self.log_error(f"Échec du redémarrage du service {service_name}")

        return success

    def reload(self, service_name):
        """
        Recharge la configuration d'un service systemd sans l'arrêter.

        Args:
            service_name: Nom du service à recharger
            root_credentials: Dictionnaire contenant les informations d'identification root (optionnel)
                             Format: {'user': 'root_username', 'password': 'root_password'}

        Returns:
            bool: True si le rechargement a réussi, False sinon
        """
        self.log_info(f"Rechargement de la configuration du service {service_name}")
        success, _, _ = self.run(['systemctl', 'reload', service_name])

        if success:
            self.log_success(f"Configuration du service {service_name} rechargée avec succès")
        else:
            # Certains services ne supportent pas reload, tenter reload-or-restart
            self.log_warning(f"Échec du rechargement simple, tentative de reload-or-restart pour {service_name}")
            success, _, _ = self.run(['systemctl', 'reload-or-restart', service_name])

            if success:
                self.log_success(f"Service {service_name} rechargé ou redémarré avec succès")
            else:
                self.log_error(f"Échec du rechargement/redémarrage du service {service_name}")

        return success

    def enable(self, service_name):
        """
        Active un service systemd au démarrage du système.

        Args:
            service_name: Nom du service à activer

        Returns:
            bool: True si l'activation a réussi, False sinon
        """
        self.log_info(f"Activation du service {service_name} au démarrage")
        success, _, _ = self.run(['systemctl', 'enable', service_name])

        if success:
            self.log_success(f"Service {service_name} activé au démarrage")
        else:
            self.log_error(f"Échec de l'activation du service {service_name} au démarrage")

        return success

    def disable(self, service_name):
        """
        Désactive un service systemd au démarrage du système.

        Args:
            service_name: Nom du service à désactiver

        Returns:
            bool: True si la désactivation a réussi, False sinon
        """
        self.log_info(f"Désactivation du service {service_name} au démarrage")
        success, _, _ = self.run(['systemctl', 'disable', service_name])

        if success:
            self.log_success(f"Service {service_name} désactivé au démarrage")
        else:
            self.log_error(f"Échec de la désactivation du service {service_name} au démarrage")
        return success