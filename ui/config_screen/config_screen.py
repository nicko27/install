from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Union
import traceback
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Label, Button, Input, TextArea, Static
from textual.widget import Widget
from ruamel.yaml import YAML

from ..choice_screen.plugin_utils import load_plugin_info, get_plugin_folder_name, get_plugin_settings_path
from ..utils.logging import get_logger

logger = get_logger('config_screen')
yaml = YAML()

class PluginConfig(App):
    """
    Écran de configuration des plugins sélectionnés.
    
    Cette classe permet la configuration de chaque plugin sélectionné
    avant leur exécution.
    """
    
    BINDINGS = [
        ("escape", "handle_escape", "Annuler"),
    ]
    
    CSS_PATH = "../styles/config.tcss"
    
    def __init__(self, plugins: List, sequence_file: Optional[str] = None):
        """
        Initialise l'écran de configuration.
        
        Args:
            plugins: Liste des plugins sélectionnés (tuples ou PluginInstance)
            sequence_file: Chemin vers le fichier de séquence (optionnel)
        """
        super().__init__()
        self.plugin_configs = plugins
        self.plugin_forms = {}
        self.current_plugin_idx = 0
        self.current_config = {}
        self.sequence_file = sequence_file
        logger.debug(f"Initialisation de l'écran de configuration avec {len(plugins)} plugins")
    
    def compose(self) -> ComposeResult:
        """
        Compose l'interface de configuration.
        
        Returns:
            ComposeResult: Résultat de la composition
        """
        with Vertical(id="config-container"):
            with Horizontal(id="config-header"):
                yield Label("Configuration des plugins", id="config-title")
                yield Label("", id="plugin-count")
                
            with Horizontal(id="config-content"):
                # Liste des plugins (gauche)
                with Vertical(id="plugin-list-container"):
                    yield Label("Plugins sélectionnés", id="plugin-list-title")
                    yield ScrollableContainer(id="plugin-list-scroll")
                
                # Formulaire de configuration (droite)
                with Vertical(id="plugin-form-container"):
                    yield Label("Configuration", id="plugin-form-title")
                    yield ScrollableContainer(id="plugin-form-scroll")
            
            # Boutons d'action
            with Horizontal(id="config-buttons"):
                yield Button("Précédent", id="prev-plugin", disabled=True)
                yield Button("Suivant", id="next-plugin")
                yield Button("Valider", id="submit-config", variant="primary")
                yield Button("Annuler", id="cancel-config", variant="error")
    
    def on_mount(self) -> None:
        """
        Actions effectuées au montage de l'écran.
        """
        logger.debug("Montage de l'écran de configuration")
        
        # Créer la liste des plugins
        self._create_plugin_list()
        
        # Afficher le premier plugin
        self._load_plugin_config(0)
        
        # Mettre à jour le compteur
        self._update_plugin_counter()
    
    def _create_plugin_list(self) -> None:
        """
        Crée la liste des plugins à configurer.
        """
        container = self.query_one("#plugin-list-scroll", ScrollableContainer)
        
        # Vider le conteneur
        container.remove_children()
        
        # Créer et ajouter les éléments de la liste
        for i, plugin_data in enumerate(self.plugin_configs):
            # Extraire le nom du plugin et l'ID d'instance selon le type de données
            if isinstance(plugin_data, tuple):
                plugin_name = plugin_data[0]
                instance_id = plugin_data[1]
            else:  # Si c'est un PluginInstance
                plugin_name = plugin_data.name
                instance_id = plugin_data.instance_id
            
            # Ignorer les séquences
            if plugin_name.startswith('__sequence__'):
                continue
                
            # Charger les informations du plugin
            plugin_info = load_plugin_info(plugin_name)
            display_name = plugin_info.get('name', plugin_name)
            
            # Créer un label cliquable
            item_id = f"plugin-item-{i}"
            item = Label(f"{display_name} ({instance_id})", id=item_id, classes="plugin-list-item")
            item.can_focus = True
            
            # Ajouter des données pour la sélection
            item.plugin_index = i
            item.plugin_name = plugin_name
            item.instance_id = instance_id
            
            # Ajouter l'élément au conteneur
            container.mount(item)
    
    def _load_plugin_config(self, plugin_idx: int) -> None:
        """
        Charge la configuration d'un plugin.
        
        Args:
            plugin_idx: Index du plugin dans la liste
        """
        if plugin_idx < 0 or plugin_idx >= len(self.plugin_configs):
            logger.error(f"Index de plugin invalide: {plugin_idx}")
            return
        
        # Mettre à jour l'index courant
        self.current_plugin_idx = plugin_idx
        
        # Sauvegarder la configuration actuelle
        self._save_current_form()
        
        # Sélectionner le plugin
        self._select_plugin_in_list(plugin_idx)
        
        # Extraire les informations du plugin
        plugin_data = self.plugin_configs[plugin_idx]
        
        # Convertir en tuple si nécessaire
        if isinstance(plugin_data, tuple):
            plugin_name, instance_id = plugin_data[0], plugin_data[1]
            plugin_config = plugin_data[2] if len(plugin_data) > 2 else {}
        else:  # Si c'est un PluginInstance
            plugin_name, instance_id = plugin_data.name, plugin_data.instance_id
            plugin_config = plugin_data.config
        
        # Ignorer les séquences
        if plugin_name.startswith('__sequence__'):
            logger.debug(f"Séquence ignorée: {plugin_name}")
            self._load_next_plugin()
            return
        
        # Créer une clé unique pour ce plugin
        plugin_key = f"{plugin_name}_{instance_id}"
        
        # Charger les informations du plugin
        plugin_info = load_plugin_info(plugin_name)
        display_name = plugin_info.get('name', plugin_name)
        
        # Mettre à jour le titre du formulaire
        form_title = self.query_one("#plugin-form-title", Label)
        form_title.update(f"Configuration de {display_name}")
        
        # Vider le conteneur du formulaire
        form_container = self.query_one("#plugin-form-scroll", ScrollableContainer)
        form_container.remove_children()
        
        # Créer et afficher le formulaire
        form = self._create_plugin_form(plugin_name, plugin_config)
        form_container.mount(form)
        
        # Stocker le formulaire
        self.plugin_forms[plugin_key] = form
        
        # Mettre à jour les boutons de navigation
        self._update_navigation_buttons()
    
    def _create_plugin_form(self, plugin_name: str, plugin_config: Dict[str, Any]) -> Static:
        """
        Crée un formulaire de configuration pour un plugin.
        
        Args:
            plugin_name: Nom du plugin
            plugin_config: Configuration actuelle du plugin
            
        Returns:
            Static: Conteneur du formulaire
        """
        form = Static(id=f"form-{plugin_name}")
        form.fields = {}
        
        try:
            # Charger le fichier settings.yml du plugin
            settings_path = get_plugin_settings_path(plugin_name)
            
            if not settings_path.exists():
                form.mount(Label(f"Pas de configuration pour {plugin_name}", classes="no-config"))
                return form
            
            # Charger les champs de configuration
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = yaml.load(f)
            
            # Extraire les champs
            if not isinstance(settings, dict) or 'fields' not in settings:
                form.mount(Label(f"Format invalide pour {plugin_name}", classes="no-config"))
                return form
            
            fields = settings.get('fields', {})
            
            # Si pas de champs
            if not fields:
                form.mount(Label(f"Pas de champs pour {plugin_name}", classes="no-config"))
                return form
            
            # Créer les champs du formulaire
            for field_name, field_props in fields.items():
                if not isinstance(field_props, dict):
                    continue
                
                field_type = field_props.get('type', 'text')
                field_label = field_props.get('label', field_name)
                field_default = field_props.get('default', '')
                field_required = field_props.get('required', False)
                field_description = field_props.get('description', '')
                
                # Créer le conteneur du champ
                field_container = Vertical(classes="field-container")
                
                # Ajouter le label
                label_text = f"{field_label}"
                if field_required:
                    label_text += " *"
                field_container.mount(Label(label_text, classes="field-label"))
                
                # Ajouter la description si présente
                if field_description:
                    field_container.mount(Label(field_description, classes="field-description"))
                
                # Déterminer la valeur actuelle
                field_value = plugin_config.get(field_name, field_default)
                
                # Créer le champ selon son type
                field_id = f"{plugin_name}-{field_name}"
                field_widget = None
                
                if field_type == 'text':
                    field_widget = Input(value=str(field_value), id=field_id, classes="field-input")
                elif field_type == 'textarea':
                    field_widget = TextArea(str(field_value), id=field_id, classes="field-textarea")
                elif field_type == 'number':
                    field_widget = Input(value=str(field_value), id=field_id, classes="field-input")
                    field_widget.type = 'number'
                elif field_type == 'checkbox':
                    # TODO: Implémenter les cases à cocher
                    field_widget = Input(value=str(field_value), id=field_id, classes="field-input")
                elif field_type == 'select':
                    # TODO: Implémenter les listes déroulantes
                    field_widget = Input(value=str(field_value), id=field_id, classes="field-input")
                else:
                    field_widget = Input(value=str(field_value), id=field_id, classes="field-input")
                
                # Ajouter le champ au conteneur
                field_container.mount(field_widget)
                
                # Ajouter le conteneur au formulaire
                form.mount(field_container)
                
                # Stocker le champ dans le dictionnaire
                form.fields[field_name] = field_widget
            
        except Exception as e:
            logger.error(f"Erreur lors de la création du formulaire pour {plugin_name}: {e}")
            logger.error(traceback.format_exc())
            form.mount(Label(f"Erreur: {str(e)}", classes="error"))
        
        return form
    
    def _select_plugin_in_list(self, plugin_idx: int) -> None:
        """
        Sélectionne un plugin dans la liste.
        
        Args:
            plugin_idx: Index du plugin à sélectionner
        """
        # Trouver tous les éléments de la liste
        items = self.query(".plugin-list-item")
        
        # Retirer la classe selected de tous les éléments
        for item in items:
            item.remove_class("selected")
            
        # Ajouter la classe selected à l'élément correspondant
        for item in items:
            if hasattr(item, 'plugin_index') and item.plugin_index == plugin_idx:
                item.add_class("selected")
                break
    
    def _save_current_form(self) -> None:
        """
        Sauvegarde les valeurs du formulaire actuel.
        """
        if self.current_plugin_idx < 0 or self.current_plugin_idx >= len(self.plugin_configs):
            return
        
        # Récupérer le plugin actuel
        plugin_data = self.plugin_configs[self.current_plugin_idx]
        
        # Convertir en tuple si nécessaire
        if isinstance(plugin_data, tuple):
            plugin_name, instance_id = plugin_data[0], plugin_data[1]
        else:  # Si c'est un PluginInstance
            plugin_name, instance_id = plugin_data.name, plugin_data.instance_id
        
        # Ignorer les séquences
        if plugin_name.startswith('__sequence__'):
            return
        
        # Créer une clé unique pour ce plugin
        plugin_key = f"{plugin_name}_{instance_id}"
        
        # Récupérer le formulaire
        form = self.plugin_forms.get(plugin_key)
        if not form:
            return
        
        # Créer un dictionnaire pour les valeurs
        values = {}
        
        # Extraire les valeurs des champs
        for field_name, field in form.fields.items():
            values[field_name] = field.value
        
        # Stocker les valeurs
        self.current_config[plugin_key] = values
    
    def _update_navigation_buttons(self) -> None:
        """
        Met à jour l'état des boutons de navigation.
        """
        prev_button = self.query_one("#prev-plugin", Button)
        next_button = self.query_one("#next-plugin", Button)
        
        # Compter les plugins (en ignorant les séquences)
        plugin_count = sum(1 for p in self.plugin_configs
                         if not (isinstance(p, tuple) and p[0].startswith('__sequence__')) and
                            not (hasattr(p, 'name') and p.name.startswith('__sequence__')))
        
        # Désactiver le bouton précédent si on est au premier plugin
        prev_button.disabled = self.current_plugin_idx <= 0
        
        # Désactiver le bouton suivant si on est au dernier plugin
        next_button.disabled = self.current_plugin_idx >= len(self.plugin_configs) - 1
    
    def _update_plugin_counter(self) -> None:
        """
        Met à jour le compteur de plugins.
        """
        counter = self.query_one("#plugin-count", Label)
        
        # Compter les plugins (en ignorant les séquences)
        plugin_count = sum(1 for p in self.plugin_configs
                         if not (isinstance(p, tuple) and p[0].startswith('__sequence__')) and
                            not (hasattr(p, 'name') and p.name.startswith('__sequence__')))
        
        # Mettre à jour le texte
        counter.update(f"Plugin {self.current_plugin_idx + 1}/{plugin_count}")
    
    def _load_next_plugin(self) -> None:
        """
        Charge le plugin suivant.
        """
        # Incrémenter l'index
        next_idx = self.current_plugin_idx + 1
        
        # Vérifier si l'index est valide
        if next_idx < len(self.plugin_configs):
            self._load_plugin_config(next_idx)
    
    def _load_prev_plugin(self) -> None:
        """
        Charge le plugin précédent.
        """
        # Décrémenter l'index
        prev_idx = self.current_plugin_idx - 1
        
        # Vérifier si l'index est valide
        if prev_idx >= 0:
            self._load_plugin_config(prev_idx)
    
    def build_config_dict(self) -> Dict[str, Any]:
        """
        Construit un dictionnaire de configuration basé sur les valeurs actuelles.
        
        Returns:
            Dict[str, Any]: Dictionnaire de configuration
        """
        # Sauvegarder le formulaire actuel
        self._save_current_form()
        
        # Le dictionnaire de configuration est déjà construit au fur et à mesure
        return self.current_config
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Gère les clics sur les boutons.
        
        Args:
            event: Événement de bouton pressé
        """
        button_id = event.button.id
        
        if button_id == "prev-plugin":
            self._load_prev_plugin()
        elif button_id == "next-plugin":
            self._load_next_plugin()
        elif button_id == "submit-config":
            await self._submit_config()
        elif button_id == "cancel-config":
            await self.action_handle_escape()
    
    async def _submit_config(self) -> None:
        """
        Valide et soumet la configuration.
        """
        # Construire le dictionnaire de configuration
        config = self.build_config_dict()
        
        # Vérifier les champs requis
        all_valid = True
        
        # TODO: Implémenter la validation des champs requis
        
        if not all_valid:
            self.notify("Certains champs requis ne sont pas remplis", severity="error")
            return
        
        # Stocker la configuration
        self.current_config = config
        
        # Retourner à l'écran précédent
        self.app.pop_screen()
    
    async def on_label_clicked(self, event: Label.Clicked) -> None:
        """
        Gère les clics sur les labels.
        
        Args:
            event: Événement de clic
        """
        # Vérifier si c'est un élément de la liste des plugins
        if hasattr(event.label, 'plugin_index'):
            self._load_plugin_config(event.label.plugin_index)
    
    async def action_handle_escape(self) -> None:
        """
        Gère l'appui sur la touche Échap.
        """
        # Demander confirmation avant de quitter
        # TODO: Implémenter une boîte de dialogue de confirmation
        
        # Retourner à l'écran précédent
        self.app.pop_screen()