# install/plugins/plugins_utils/config_files.py
#!/usr/bin/env python3
"""
Module utilitaire pour lire et écrire différents formats de fichiers de configuration
(INI, JSON) et manipuler des fichiers texte ligne par ligne.
La prise en charge de YAML a été supprimée car ruamel.yaml n'est pas disponible.
"""

from plugins_utils.plugins_utils_base import PluginsUtilsBase
import os
import re
import json
import configparser
import tempfile
import shutil
import shlex # Pour échapper les arguments de commande
import time # Ajout de l'import time manquant pour _backup_file
from pathlib import Path
from typing import Union, Optional, List, Dict, Any, Tuple, Generator

# ruamel.yaml n'est pas disponible
RUAMEL_YAML_AVAILABLE = False

class ConfigFileCommands(PluginsUtilsBase):
    """
    Classe pour lire et écrire des fichiers de configuration (INI, JSON)
    et manipuler des fichiers texte.
    Hérite de PluginUtilsBase pour l'exécution de commandes (pour les backups/perms).
    """

    def __init__(self, logger=None, target_ip=None):
        """Initialise le gestionnaire de fichiers de configuration."""
        super().__init__(logger, target_ip)
        # Pas d'initialisation YAML ici

    def _backup_file(self, path: Union[str, Path]) -> Optional[str]:
        """Crée une sauvegarde d'un fichier."""
        file_path = Path(path)
        if not file_path.exists():
            # Utiliser self.run pour vérifier l'existence, car os.path peut échouer avec sudo
            success_test, _, _ = self.run(['test', '-e', str(file_path)], check=False, no_output=True, error_as_warning=True, needs_sudo=True)
            if not success_test:
                 self.log_debug(f"Fichier {file_path} non trouvé (vérifié via test -e), pas de sauvegarde nécessaire.")
                 return None
            # Si test -e réussit mais exists() échoue, il y a un problème de permission potentiel
            # On continue quand même la tentative de sauvegarde

        backup_path = file_path.with_suffix(f"{file_path.suffix}.bak_{int(time.time())}")
        try:
            # Utiliser cp -a pour préserver les métadonnées et gérer sudo
            cmd_cp = ['cp', '-a', str(file_path), str(backup_path)]
            success, _, stderr = self.run(cmd_cp, check=False, needs_sudo=True)
            if not success:
                 self.log_warning(f"Échec de la création de la sauvegarde {backup_path}. Stderr: {stderr}")
                 return None
            self.log_debug(f"Sauvegarde créée: {backup_path}")
            return str(backup_path)
        except Exception as e:
            self.log_error(f"Erreur lors de la création de la sauvegarde pour {file_path}: {e}", exc_info=True)
            return None

    def _write_file_content(self, path: Union[str, Path], content: str, backup: bool) -> bool:
        """Écrit du contenu dans un fichier, avec sauvegarde optionnelle et gestion sudo."""
        file_path = Path(path)
        self.log_debug(f"Écriture dans le fichier: {file_path}")

        backup_file = None
        original_stat: Optional[str] = None # Modifié pour stocker la chaîne UID:GID:Mode
        # Tenter de lire les stats avant sauvegarde/écriture pour restaurer perms/owner
        try:
            # Utiliser stat via self.run pour gérer sudo si nécessaire
            cmd_stat = ['stat', '-c', '%u:%g:%a', str(file_path)] # Format UID:GID:OctalPerms
            stat_success, stat_stdout, _ = self.run(cmd_stat, check=False, no_output=True, error_as_warning=True, needs_sudo=True) # error_as_warning pour ignorer "No such file"
            if stat_success and stat_stdout.strip():
                 original_stat = stat_stdout.strip() # Ex: "1000:1000:644"
                 self.log_debug(f"Statistiques originales de {file_path}: {original_stat}")
            elif file_path.exists(): # Si le fichier existe mais stat échoue (permissions?)
                self.log_warning(f"Impossible de lire les statistiques originales de {file_path} (commande stat échouée).")

        except Exception as e_stat_read:
             self.log_warning(f"Impossible de lire les statistiques originales de {file_path}: {e_stat_read}")


        if backup:
            backup_file = self._backup_file(file_path)
            # Si la sauvegarde réussit et qu'on n'avait pas les stats, les prendre de la sauvegarde
            if backup_file and not original_stat:
                 try:
                      cmd_stat_bak = ['stat', '-c', '%u:%g:%a', backup_file]
                      stat_success_bak, stat_stdout_bak, _ = self.run(cmd_stat_bak, check=False, no_output=True, needs_sudo=True)
                      if stat_success_bak and stat_stdout_bak.strip():
                           original_stat = stat_stdout_bak.strip()
                           self.log_debug(f"Statistiques originales récupérées de la sauvegarde {backup_file}: {original_stat}")
                 except Exception as e_stat_bak:
                      self.log_warning(f"Impossible de lire les statistiques de la sauvegarde {backup_file}: {e_stat_bak}")


        # Écrire dans un fichier temporaire d'abord
        tmp_file_path: Optional[Path] = None
        try:
            # Créer un fichier temporaire sécurisé
            fd, tmp_file = tempfile.mkstemp(suffix=".tmp", text=True)
            os.close(fd) # Fermer le descripteur immédiatement
            tmp_file_path = Path(tmp_file)
            tmp_file_path.write_text(content, encoding='utf-8')
            self.log_debug(f"Contenu écrit dans le fichier temporaire: {tmp_file_path}")

            # Déplacer le fichier temporaire vers la destination finale avec sudo
            # Utiliser `cp` puis `chmod/chown` pour mieux gérer les permissions/propriétaires
            cmd_cp = ['cp', str(tmp_file_path), str(file_path)]
            success_cp, _, stderr_cp = self.run(cmd_cp, check=False, needs_sudo=True)
            if not success_cp:
                 self.log_error(f"Échec de la copie vers {file_path}. Stderr: {stderr_cp}")
                 # Ne supprime pas le fichier temporaire ici pour investigation potentielle
                 return False # Ne pas continuer si la copie échoue

            # Tenter de restaurer propriétaire/groupe/permissions si on a les infos
            if original_stat:
                 try:
                      uid, gid, mode_octal = original_stat.split(':')
                      # Vérifier si mode_octal est valide avant de l'utiliser
                      if re.match(r'^[0-7]{3,4}$', mode_octal):
                            self.run(['chown', f"{uid}:{gid}", str(file_path)], needs_sudo=True, check=False)
                            self.run(['chmod', mode_octal, str(file_path)], needs_sudo=True, check=False)
                            self.log_debug(f"Permissions/propriétaire restaurés sur {file_path} vers {original_stat}")
                      else:
                          self.log_warning(f"Mode octal invalide '{mode_octal}' obtenu de stat, utilisation de 644 par défaut.")
                          self.run(['chown', f"{uid}:{gid}", str(file_path)], needs_sudo=True, check=False)
                          self.run(['chmod', '644', str(file_path)], needs_sudo=True, check=False)
                 except Exception as e_restore:
                      self.log_warning(f"Impossible de restaurer les permissions/propriétaire originaux ({original_stat}): {e_restore}")
                      # Appliquer des permissions par défaut si la restauration échoue
                      self.run(['chmod', '644', str(file_path)], needs_sudo=True, check=False)
            else:
                 # Définir des permissions par défaut raisonnables (ex: 644) si aucune info originale
                 self.log_debug(f"Aucune information originale sur les permissions/propriétaire trouvée, application de 644 par défaut.")
                 self.run(['chmod', '644', str(file_path)], needs_sudo=True, check=False)

            self.log_success(f"Fichier {file_path} écrit/mis à jour avec succès.")
            return True

        except Exception as e:
            self.log_error(f"Erreur lors de l'écriture dans {file_path}: {e}", exc_info=True)
            return False
        finally:
            # Nettoyer le fichier temporaire
            if tmp_file_path and tmp_file_path.exists():
                try: tmp_file_path.unlink()
                except Exception as e_unlink:
                     self.log_warning(f"Impossible de supprimer le fichier temporaire {tmp_file_path}: {e_unlink}")

    # --- Méthodes INI ---
    def _manual_ini_parse(self, content: str) -> Dict[str, Dict[str, str]]:
        """Parse manuellement un fichier INI simple ligne par ligne."""
        self.log_debug("Tentative de parsing INI manuel simplifié.")
        data = {'DEFAULT': {}} # Utiliser une section DEFAULT par défaut
        current_section = 'DEFAULT'
        for line in content.splitlines():
            line_strip = line.strip()
            # Ignorer commentaires et lignes vides
            if not line_strip or line_strip.startswith('#') or line_strip.startswith(';'):
                continue
            # Détecter les sections (simpliste)
            if line_strip.startswith('[') and line_strip.endswith(']'):
                section_name = line_strip[1:-1].strip()
                if section_name:
                    current_section = section_name
                    if current_section not in data:
                        data[current_section] = {}
                continue
            # Chercher le premier '=' comme délimiteur clé/valeur
            if '=' in line_strip:
                key, value = line_strip.split('=', 1)
                key = key.strip()
                value = value.strip()
                # Optionnel : supprimer les guillemets autour de la valeur
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                if key: # Ignorer si clé vide
                    data[current_section][key] = value
            # Ignorer les lignes qui ne sont ni section ni clé=valeur
            # else:
            #    self.log_warning(f"Ligne ignorée lors du parsing manuel : '{line_strip}'")
        # Supprimer la section DEFAULT si elle est vide et qu'il y a d'autres sections
        if 'DEFAULT' in data and not data['DEFAULT'] and len(data) > 1:
            del data['DEFAULT']
        return data


    def read_ini_file(self, path: Union[str, Path]) -> Optional[Dict[str, Dict[str, str]]]:
        """Lit un fichier INI et le retourne sous forme de dictionnaire imbriqué.
           Gère les fichiers sans section d'en-tête via [DEFAULT].
           Tente un parsing manuel si configparser échoue silencieusement.
        """
        file_path = Path(path)
        self.log_debug(f"Lecture du fichier INI: {file_path}")
        # Lire le contenu du fichier (peut nécessiter sudo)
        success_read, content, stderr_read = self.run(['cat', str(file_path)], check=False, needs_sudo=False, no_output=True, error_as_warning=True)
        if not success_read:
             if "no such file" in stderr_read.lower():
                  self.log_error(f"Fichier INI introuvable: {file_path}")
             else:
                  self.log_error(f"Impossible de lire le fichier INI {file_path}. Stderr: {stderr_read}")
             return None

        # 1. Essayer avec configparser (non strict)
        config = configparser.ConfigParser(interpolation=None, strict=False)
        config_dict: Optional[Dict[str, Dict[str, str]]] = None
        processed_content = content # Garder une copie pour le parsing manuel
        try:
            needs_default_section = True
            has_content = False
            for line in content.splitlines():
                line_strip = line.strip()
                if not line_strip or line_strip.startswith('#') or line_strip.startswith(';'): continue
                has_content = True
                if line_strip.startswith('['): needs_default_section = False; break

            if has_content and needs_default_section:
                self.log_debug(f"Aucune section détectée via configparser, ajout de [DEFAULT].")
                processed_content = "[DEFAULT]\n" + content

            config.read_string(processed_content)
            # Convertir en dictionnaire standard
            parsed_dict = {section: dict(config.items(section)) for section in config.sections()}

            # Vérifier si le parsing a réussi mais retourné un dict vide alors qu'il y avait du contenu
            if has_content and not parsed_dict:
                self.log_warning(f"Configparser a retourné un résultat vide pour {file_path} malgré du contenu. Tentative de parsing manuel.")
                # Passer au parsing manuel
            else:
                config_dict = parsed_dict # Le parsing a fonctionné (même si vide pour fichier vide)

        except configparser.Error as e:
            # Erreur de parsing explicite, tenter le parsing manuel
            self.log_warning(f"Erreur de parsing INI standard dans {file_path}: {e}. Tentative de parsing manuel.")
        except Exception as e:
            # Autre erreur inattendue, tenter le parsing manuel
            self.log_warning(f"Erreur inattendue lors du parsing INI standard pour {file_path}: {e}. Tentative de parsing manuel.")

        # 2. Essayer le parsing manuel si configparser a échoué ou retourné vide pour un fichier non vide
        if config_dict is None or (has_content and not config_dict):
            try:
                config_dict = self._manual_ini_parse(content) # Utiliser le contenu original
                if not config_dict or ('DEFAULT' in config_dict and not config_dict['DEFAULT'] and len(config_dict)==1): # Vérifier si le parsing manuel a aussi échoué
                     # Retourner vide dans ce cas plutôt que None, car le fichier existe et a été lu
                     config_dict = {}
                else:
                     self.log_debug(f"Parsing INI réussi via la méthode manuelle pour {file_path}.")

            except Exception as manual_e:
                self.log_error(f"Le parsing manuel a également échoué pour {file_path}: {manual_e}", exc_info=True)
                return None # Échec des deux méthodes

        self.log_debug(f"Contenu INI final lu: {config_dict}")
        return config_dict if config_dict is not None else {} # Retourner {} si fichier vide ou parsing échoué mais fichier lu

    def get_ini_value(self, path: Union[str, Path], section: str, key: str, default: Optional[str] = None) -> Optional[str]:
        """Récupère une valeur spécifique d'un fichier INI."""
        config_dict = self.read_ini_file(path)
        if config_dict is None:
            # Si la lecture échoue mais que le fichier n'existe pas, retourner default
             # Utiliser self.run car Path().exists() peut échouer avec sudo
             success_test, _, _ = self.run(['test', '-e', str(path)], check=False, no_output=True, error_as_warning=True, needs_sudo=True)
             if not success_test:
                  return default
             return None # Erreur de lecture/parsing
        # Si la section DEFAULT a été ajoutée implicitement, la vérifier aussi
        value = config_dict.get(section, {}).get(key)
        if value is None and section != 'DEFAULT':
             value = config_dict.get('DEFAULT', {}).get(key)

        return value if value is not None else default

    def set_ini_value(self, path: Union[str, Path], section: str, key: str, value: Optional[str],
                      create_section: bool = True, backup: bool = True) -> bool:
        """Définit ou supprime une valeur dans un fichier INI."""
        file_path = Path(path)
        action = "Suppression de" if value is None else "Définition de"
        self.log_debug(f"{action} la clé INI '{key}' dans la section '[{section}]' du fichier: {file_path}")
        if value is not None: self.log_debug(f"  Nouvelle valeur: '{value}'")

        config = configparser.ConfigParser(interpolation=None)
        # Lire le contenu existant (si possible), en gérant l'absence de section
        current_content = ""
        read_success = False
        if file_path.exists(): # Utiliser exists() ici, la lecture avec cat gérera sudo
             read_success, content_read, stderr_read = self.run(['cat', str(file_path)], check=False, needs_sudo=True, no_output=True, error_as_warning=True)
             if read_success:
                  current_content = content_read
             elif "no such file" not in stderr_read.lower():
                  self.log_warning(f"Impossible de lire le contenu existant de {file_path} avant modification. Stderr: {stderr_read}")
                  # Continuer avec un parser vide, le fichier sera écrasé

        # Prétraitement pour ajouter [DEFAULT] si nécessaire
        original_needs_default = False
        processed_content = current_content
        if read_success and current_content:
            needs_default_section = True
            has_content = False
            for line in current_content.splitlines():
                line_strip = line.strip()
                if not line_strip or line_strip.startswith('#') or line_strip.startswith(';'): continue
                has_content = True
                if line_strip.startswith('['): needs_default_section = False; break
            if has_content and needs_default_section:
                processed_content = "[DEFAULT]\n" + current_content
                original_needs_default = True

        try:
            config.read_string(processed_content)
        except configparser.Error as e:
            self.log_warning(f"Erreur de parsing INI lors de la lecture de {file_path}: {e}. Le contenu existant sera perdu si l'écriture réussit.")
            config = configparser.ConfigParser(interpolation=None) # Réinitialiser

        # Vérifier/Créer la section (utiliser la section demandée, même si c'était sous [DEFAULT])
        target_section = section if section else 'DEFAULT' # Utiliser DEFAULT si section est vide/None
        if not config.has_section(target_section):
            if create_section:
                self.log_debug(f"Création de la section INI: [{target_section}]")
                config.add_section(target_section)
            else:
                self.log_error(f"La section INI '[{target_section}]' n'existe pas et create_section=False.")
                return False

        # Définir ou supprimer la valeur
        try:
            if value is None:
                if config.has_option(target_section, key):
                    config.remove_option(target_section, key)
                    self.log_debug(f"Clé '{key}' supprimée de la section '[{target_section}]'.")
                else:
                    self.log_debug(f"Clé '{key}' n'existait pas dans la section '[{target_section}]'.")
            else:
                config.set(target_section, key, str(value)) # Assurer que la valeur est une chaîne
                self.log_debug(f"Clé '{key}' définie à '{value}' dans la section '[{target_section}]'.")
        except Exception as e:
             self.log_error(f"Erreur lors de la modification de la configuration INI en mémoire: {e}")
             return False

        # Écrire le contenu modifié dans une chaîne
        try:
            from io import StringIO
            string_io = StringIO()
            config.write(string_io)
            new_content = string_io.getvalue()

            # Si l'original n'avait pas de section, et qu'on a écrit seulement dans [DEFAULT],
            # on retire l'en-tête [DEFAULT] du contenu final.
            if original_needs_default and config.sections() == ['DEFAULT']:
                 lines = new_content.splitlines()
                 if lines[0].strip() == '[DEFAULT]':
                      new_content = "\n".join(lines[1:])
                      self.log_debug("En-tête [DEFAULT] retiré avant l'écriture car fichier original sans section.")

        except Exception as e:
             self.log_error(f"Erreur lors de la génération du contenu INI: {e}")
             return False

        # Écrire le fichier final
        return self._write_file_content(file_path, new_content, backup=backup)

    # --- Méthodes YAML (Supprimées car ruamel.yaml n'est pas disponible) ---
    # def read_yaml_file(...): pass
    # def write_yaml_file(...): pass

    # --- Méthodes JSON ---

    def read_json_file(self, path: Union[str, Path]) -> Optional[Any]:
        """Lit un fichier JSON et le retourne comme objet Python."""
        file_path = Path(path)
        self.log_debug(f"Lecture du fichier JSON: {file_path}")
        # Lire le contenu (peut nécessiter sudo)
        success_read, content, stderr_read = self.run(['cat', str(file_path)], check=False, needs_sudo=True, no_output=True, error_as_warning=True) # error_as_warning
        if not success_read:
             if "no such file" in stderr_read.lower():
                  self.log_error(f"Fichier JSON introuvable: {file_path}")
             else:
                  self.log_error(f"Impossible de lire le fichier JSON {file_path}. Stderr: {stderr_read}")
             return None
        try:
            data = json.loads(content)
            self.log_debug(f"Contenu JSON lu avec succès.")
            return data
        except json.JSONDecodeError as e:
            self.log_error(f"Erreur de parsing JSON dans {file_path}: {e}")
            return None
        except Exception as e:
            self.log_error(f"Erreur inattendue lors du parsing JSON pour {file_path}: {e}", exc_info=True)
            return None

    def write_json_file(self, path: Union[str, Path], data: Any, indent: Optional[int] = 2, backup: bool = True) -> bool:
        """Écrit un objet Python dans un fichier JSON."""
        file_path = Path(path)
        self.log_debug(f"Écriture des données JSON dans: {file_path}")

        # Générer le contenu JSON dans une chaîne
        try:
            # Utiliser ensure_ascii=False pour un meilleur support UTF-8
            json_content = json.dumps(data, indent=indent, ensure_ascii=False) + "\n"
        except Exception as e:
             self.log_error(f"Erreur lors de la génération du contenu JSON: {e}")
             return False

        # Écrire le fichier final
        return self._write_file_content(file_path, json_content, backup=backup)

    # --- Méthodes Fichiers Texte Génériques ---

    def read_file_lines(self, path: Union[str, Path]) -> Optional[List[str]]:
        """Lit toutes les lignes d'un fichier texte."""
        file_path = Path(path)
        self.log_debug(f"Lecture des lignes du fichier: {file_path}")
        # Lire avec sudo si nécessaire
        success_read, content, stderr_read = self.run(['cat', str(file_path)], check=False, needs_sudo=True, no_output=True, error_as_warning=True) # error_as_warning
        if not success_read:
             if "no such file" in stderr_read.lower():
                  self.log_error(f"Fichier introuvable: {file_path}")
             else:
                  self.log_error(f"Impossible de lire le fichier {file_path}. Stderr: {stderr_read}")
             return None
        # Retourner les lignes en gardant les fins de ligne originales
        return content.splitlines(keepends=True)

    def get_line_containing(self, path: Union[str, Path], pattern: str, first_match_only: bool = True) -> Union[Optional[str], List[str], None]:
        """Trouve la première ou toutes les lignes contenant un motif regex."""
        lines = self.read_file_lines(path)
        if lines is None: return None

        self.log_debug(f"Recherche du pattern '{pattern}' dans {path}")
        found_lines = []
        try:
            regex = re.compile(pattern)
            for line in lines:
                if regex.search(line):
                    # Rstrip seulement pour le retour, garder la ligne originale pour l'écriture
                    line_clean = line.rstrip('\n')
                    if first_match_only:
                        return line_clean
                    found_lines.append(line_clean)
            return found_lines if found_lines else ([] if not first_match_only else None)
        except re.error as e:
             self.log_error(f"Erreur de regex dans le pattern '{pattern}': {e}")
             return None

    def replace_line(self, path: Union[str, Path], pattern: str, new_line: str, replace_all: bool = False, backup: bool = True) -> bool:
        """Remplace la première ou toutes les lignes correspondant à un motif regex."""
        file_path = Path(path)
        self.log_debug(f"Remplacement des lignes correspondant à '{pattern}' dans {file_path}")
        lines = self.read_file_lines(file_path)
        if lines is None: return False

        new_lines = []
        modified = False
        replaced_count = 0
        try:
            regex = re.compile(pattern)
            # S'assurer que la nouvelle ligne a une fin de ligne
            new_line_with_eol = new_line.rstrip('\n') + '\n'
            for line in lines:
                # Utiliser search pour trouver le pattern n'importe où dans la ligne
                if regex.search(line) and (replace_all or replaced_count == 0):
                    new_lines.append(new_line_with_eol)
                    modified = True
                    replaced_count += 1
                    self.log_debug(f"  Ligne remplacée: {line.strip()} -> {new_line.strip()}")
                else:
                    new_lines.append(line) # Garder la ligne originale avec sa fin de ligne

            if not modified:
                 self.log_debug("Aucune ligne correspondante trouvée pour remplacement.")
                 return True # Pas d'erreur si rien à remplacer

            # Écrire le contenu modifié
            return self._write_file_content(file_path, "".join(new_lines), backup=backup)

        except re.error as e:
             self.log_error(f"Erreur de regex dans le pattern '{pattern}': {e}")
             return False
        except Exception as e:
             self.log_error(f"Erreur lors du remplacement dans {file_path}: {e}", exc_info=True)
             return False

    def comment_line(self, path: Union[str, Path], pattern: str, comment_char: str = '#', backup: bool = True) -> bool:
        """Commente les lignes correspondant à un motif regex."""
        file_path = Path(path)
        self.log_debug(f"Commentage des lignes correspondant à '{pattern}' dans {file_path}")
        lines = self.read_file_lines(file_path)
        if lines is None: return False

        new_lines = []
        modified = False
        try:
            regex = re.compile(pattern)
            for line in lines:
                line_strip = line.strip()
                # Ne commenter que si elle correspond ET n'est pas déjà commentée (ou vide)
                if line_strip and not line_strip.startswith(comment_char) and regex.search(line):
                    # Préserver l'indentation originale
                    indent = line[:len(line) - len(line.lstrip())]
                    new_lines.append(f"{indent}{comment_char} {line_strip}\n")
                    modified = True
                    self.log_debug(f"  Ligne commentée: {line_strip}")
                else:
                    new_lines.append(line) # Garder la ligne originale

            if not modified:
                 self.log_debug("Aucune ligne à commenter trouvée.")
                 return True

            # Écrire le contenu modifié
            return self._write_file_content(file_path, "".join(new_lines), backup=backup)

        except re.error as e:
             self.log_error(f"Erreur de regex dans le pattern '{pattern}': {e}")
             return False
        except Exception as e:
             self.log_error(f"Erreur lors du commentage dans {file_path}: {e}", exc_info=True)
             return False

    def uncomment_line(self, path: Union[str, Path], pattern: str, comment_char: str = '#', backup: bool = True) -> bool:
        """Décommente les lignes correspondant à un motif regex."""
        file_path = Path(path)
        self.log_debug(f"Décommentage des lignes correspondant à '{pattern}' dans {file_path}")
        lines = self.read_file_lines(file_path)
        if lines is None: return False

        new_lines = []
        modified = False
        try:
            regex = re.compile(pattern)
            # Regex pour trouver le commentaire au début (avec ou sans espace après)
            comment_regex = re.compile(r"^(\s*)" + re.escape(comment_char) + r"\s*(.*)")
            for line in lines:
                match_comment = comment_regex.match(line)
                # Vérifier si la ligne est commentée ET si le contenu décommenté correspond au pattern
                if match_comment:
                     indent, uncommented_content = match_comment.groups()
                     if regex.search(uncommented_content): # Vérifier le pattern sur le contenu décommenté
                          new_lines.append(f"{indent}{uncommented_content}\n") # Restaurer indentation
                          modified = True
                          self.log_debug(f"  Ligne décommentée: {line.strip()}")
                     else:
                          new_lines.append(line) # Ne correspond pas au pattern, garder commenté
                else:
                    new_lines.append(line) # Pas commenté, garder tel quel

            if not modified:
                 self.log_debug("Aucune ligne à décommenter trouvée.")
                 return True

            # Écrire le contenu modifié
            return self._write_file_content(file_path, "".join(new_lines), backup=backup)

        except re.error as e:
             self.log_error(f"Erreur de regex dans le pattern '{pattern}': {e}")
             return False
        except Exception as e:
             self.log_error(f"Erreur lors du décommentage dans {file_path}: {e}", exc_info=True)
             return False

    def append_line(self, path: Union[str, Path], line_to_append: str, ensure_newline: bool = True) -> bool:
        """Ajoute une ligne à la fin d'un fichier."""
        file_path = Path(path)
        self.log_debug(f"Ajout de la ligne à la fin de {file_path}: {line_to_append[:50]}...")

        content_to_append = line_to_append
        if ensure_newline and not content_to_append.endswith('\n'):
            content_to_append += '\n'

        # Utiliser tee -a pour ajouter (gère sudo)
        cmd_append = ['tee', '-a', str(file_path)]
        # Passer le contenu via stdin
        success, stdout, stderr = self.run(cmd_append, input_data=content_to_append, check=False, needs_sudo=True)

        if success:
            self.log_success(f"Ligne ajoutée avec succès à {file_path}.")
            return True
        else:
            self.log_error(f"Échec de l'ajout de la ligne à {file_path}. Stderr: {stderr}")
            return False

    def ensure_line_exists(self, path: Union[str, Path], line_to_ensure: str, pattern_to_check: Optional[str] = None, backup: bool = True) -> bool:
        """
        S'assure qu'une ligne spécifique existe dans un fichier, l'ajoute sinon.

        Args:
            path: Chemin du fichier.
            line_to_ensure: La ligne exacte qui doit exister (sera ajoutée si absente).
            pattern_to_check: Regex pour vérifier l'existence. Si None, utilise line_to_ensure littéralement.
            backup: Créer une sauvegarde si le fichier est modifié.

        Returns:
            bool: True si la ligne existe ou a été ajoutée avec succès.
        """
        file_path = Path(path)
        self.log_debug(f"Vérification/Ajout de la ligne dans {file_path}: {line_to_ensure[:50]}...")

        # 1. Lire le contenu actuel
        current_content = ""
        read_success, content_read, stderr_read = self.run(['cat', str(file_path)], check=False, needs_sudo=True, no_output=True, error_as_warning=True)
        if read_success:
             current_content = content_read
        elif "no such file" not in stderr_read.lower():
             # Erreur autre que fichier non trouvé
             self.log_error(f"Impossible de lire {file_path} pour vérification. Stderr: {stderr_read}")
             return False
        # Si le fichier n'existe pas, current_content reste ""

        # 2. Vérifier l'existence
        line_exists = False
        try:
            check_pattern = pattern_to_check if pattern_to_check else r'^' + re.escape(line_to_ensure.strip()) + r'\s*$'
            if re.search(check_pattern, current_content, re.MULTILINE):
                line_exists = True
        except re.error as e:
             self.log_error(f"Erreur de regex dans le pattern '{pattern_to_check}': {e}")
             return False

        # 3. Ajouter si nécessaire
        if line_exists:
            return True
        else:
            # Ajouter la ligne avec un saut de ligne avant si nécessaire
            new_content = current_content
            if current_content and not current_content.endswith('\n'):
                 new_content += '\n'
            new_content += line_to_ensure.rstrip('\n') + '\n'

            return self._write_file_content(file_path, new_content, backup=backup)