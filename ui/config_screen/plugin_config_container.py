from textual.app import ComposeResult
from textual.widgets import Label, Checkbox
from textual.containers import Vertical, Horizontal, VerticalGroup, HorizontalGroup
from logging import getLogger

logger = getLogger('plugin_config_container')

from .config_container import ConfigContainer
from .text_field import TextField
from .directory_field import DirectoryField
from .ip_field import IPField
from .checkbox_field import CheckboxField
from .select_field import SelectField
from .checkbox_group_field import CheckboxGroupField
from .template_field import TemplateField
from .template_manager import TemplateManager



class PluginConfigContainer(ConfigContainer):
    """Conteneur pour les champs de configuration des plugins"""

    def __init__(self, plugin: str, name: str, icon: str, description: str,
                 fields_by_plugin: dict, fields_by_id: dict, config_fields: list, **kwargs):
        logger.debug(f"Initialisation du conteneur de configuration pour {plugin}")
        super().__init__(
            source_id=plugin,
            title=name,
            icon=icon,
            description=description,
            fields_by_id=fields_by_id,
            config_fields=config_fields,
            is_global=False,
            **kwargs
        )
        # Garder une référence aux collections de champs spécifiques au plugin
        self.fields_by_plugin = fields_by_plugin
        if plugin not in fields_by_plugin:
            fields_by_plugin[plugin] = {}
            logger.debug(f"Nouvelle collection de champs créée pour {plugin}")
        
        # Champ d'exécution distante (sera défini par PluginConfig si nécessaire)
        self.remote_field = None
        
        # Initialiser le gestionnaire de templates
        self.template_manager = TemplateManager()
        logger.debug(f"Gestionnaire de templates initialisé pour {plugin}")

    def compose(self) -> ComposeResult:
        """Compose le conteneur avec les champs et la case à cocher d'exécution distante si disponible"""
        logger.debug(f"Composition du conteneur pour {self.source_id}")
        
        # Titre et description
        with VerticalGroup(classes="config-header"):
            yield Label(f"{self.icon} {self.title}", classes="config-title")
            if self.description:
                yield Label(self.description, classes="config-description")

        if not self.config_fields and not self.remote_field:
            logger.debug(f"Aucun champ de configuration pour {self.source_id}")
            with VerticalGroup(classes="no-config"):
                with HorizontalGroup(classes="no-config-content"):
                    yield Label("ℹ️", classes="no-config-icon")
                    yield Label(f"Rien à configurer pour ce plugin", classes="no-config-label")
                return

        with VerticalGroup(classes="config-fields"):
            # Vérifier et ajouter le champ de template s'il y a des templates disponibles
            templates = self.template_manager.get_plugin_templates(self.source_id)
            if templates:
                logger.debug(f"Templates trouvés pour {self.source_id} : {list(templates.keys())}")
                template_field = TemplateField(self.source_id, 'template', self.fields_by_id)
                yield template_field
            else:
                logger.debug(f"Aucun template trouvé pour {self.source_id}")
            # Champs de configuration
            for field_config in self.config_fields:
                field_id = field_config.get('id')
                if not field_id:
                    logger.warning(f"Champ sans identifiant dans {self.source_id}")
                    continue
                    
                field_type = field_config.get('type', 'text')
                logger.debug(f"Création du champ {field_id} de type {field_type}")
                
                field_class = {
                    'text': TextField,
                    'directory': DirectoryField,
                    'ip': IPField,
                    'checkbox': CheckboxField,
                    'select': SelectField,
                    'checkbox_group': CheckboxGroupField
                }.get(field_type, TextField)

                # Créer le champ avec accès aux autres champs
                field = field_class(self.source_id, field_id, field_config, self.fields_by_id, is_global=self.is_global)
                self.fields_by_id[field_id] = field
                logger.debug(f"Champ {field_id} créé et ajouté au dictionnaire")
                
                # IMPORTANT: Ne pas appliquer les valeurs prédéfinies ici
                # Les valeurs seront appliquées dans on_mount() quand tous les widgets seront créés

                # Si c'est une case à cocher, ajouter le gestionnaire d'événements
                if field_type in ['checkbox', 'checkbox_group']:
                    field.on_checkbox_changed = self.on_checkbox_changed
                    logger.debug(f"Gestionnaire d'événements ajouté pour {field_id}")

                yield field
            
            # Si nous avons un champ d'exécution distante, l'ajouter à la fin du conteneur
            if self.remote_field:
                logger.debug(f"Ajout du champ d'exécution distante pour {self.source_id}")
                with VerticalGroup(classes="remote-execution-container"):
                    yield self.remote_field

    def on_mount(self) -> None:
        """Appelé quand le conteneur est monté, après la création des widgets"""
        logger.debug(f"Montage du conteneur pour {self.source_id}")
        
        # Maintenant que les widgets sont créés, appliquer les valeurs prédéfinies
        self._apply_predefined_values()
        
    def _apply_predefined_values(self) -> None:
        """Applique les valeurs prédéfinies aux champs"""
        logger.debug(f"Application des valeurs prédéfinies pour {self.source_id}")
        
        # Vérifier que nous sommes dans l'écran de configuration
        config_screen = self.app.screen if hasattr(self, 'app') and self.app else None
        if not config_screen or not hasattr(config_screen, 'current_config'):
            logger.warning(f"Impossible d'accéder à current_config pour {self.source_id}")
            return
            
        # Récupérer l'ID de l'instance du plugin
        plugin_instance_id = self.id.replace('plugin_', '')
        if plugin_instance_id not in config_screen.current_config:
            logger.warning(f"Pas de configuration trouvée pour l'instance {plugin_instance_id}")
            return
            
        # Récupérer la configuration prédéfinie pour cette instance
        predefined_config = config_screen.current_config[plugin_instance_id]
        logger.debug(f"Configuration trouvée pour {plugin_instance_id}: {predefined_config}")
        
        # Parcourir tous les champs de configuration
        for field_config in self.config_fields:
            field_id = field_config.get('id')
            if not field_id or field_id not in self.fields_by_id:
                logger.warning(f"Champ {field_id} non trouvé dans fields_by_id")
                continue
                
            field = self.fields_by_id[field_id]
            variable_name = field_config.get('variable', field_id)
            
            try:
                # Déterminer la valeur à appliquer en fonction du format de configuration
                predefined_value = None
                
                # Format 1: Utilisation de 'config' (nouveau format) 
                if 'config' in predefined_config and variable_name in predefined_config['config']:
                    predefined_value = predefined_config['config'][variable_name]
                    logger.debug(f"Valeur trouvée dans 'config': {predefined_value}")
                    
                # Format 2: Valeurs au niveau racine (ancien format / rétrocompatibilité)
                elif variable_name in predefined_config:
                    predefined_value = predefined_config[variable_name]
                    logger.debug(f"Valeur trouvée à la racine: {predefined_value}")
                    
                # Si une valeur a été trouvée, l'appliquer au champ
                if predefined_value is not None:
                    self._apply_value_to_field(field, field_config, predefined_value)
            except Exception as e:
                logger.error(f"Erreur lors de l'application de la valeur pour {field_id}: {e}")
                import traceback
                logger.error(traceback.format_exc())
    
    def _apply_value_to_field(self, field, field_config, value):
        """Applique une valeur à un champ spécifique avec gestion des cas particuliers"""
        field_id = field_config.get('id')
        field_type = field_config.get('type', 'text')
        
        logger.debug(f"💾 Application de '{value}' au champ {field_id} (type={field_type})")
        
        try:
            # Cas spécial: champ IP - Besoin d'une attention particulière
            if field_type == 'ip':
                # S'assurer que la valeur est une chaîne
                value_str = str(value) if value is not None else ""
                logger.debug(f"🔎 Traitement spécial pour champ IP {field_id} avec valeur '{value_str}'")
                
                # Appliquer la valeur avec priorité maximale
                # Force update_dependencies=True pour s'assurer que les dépendances sont mises à jour
                success = field.set_value(value_str, update_dependencies=True)
                
                # Vérification supplémentaire pour s'assurer que la valeur a bien été appliquée
                if hasattr(field, '_internal_value'):
                    logger.debug(f"✅ Vérification: valeur interne de {field_id} est '{field._internal_value}'")
                else:
                    logger.warning(f"⚠️ Champ IP {field_id} n'a pas d'attribut _internal_value")
                    
                logger.debug(f"Résultat de l'application IP pour {field_id}: {success}")
                
            # Cas spécial: champ select avec options dynamiques
            elif field_type == 'select' and not hasattr(field, 'input'):
                # Stocker la valeur pour l'appliquer plus tard
                logger.debug(f"Stockage de la valeur pour le select {field_id} sans input")
                # Utiliser set_value plutôt que d'assigner directement field.value
                field.set_value(value, update_input=False)  # Le widget n'existe pas encore
                # Programmer une application différée
                field.call_later(lambda f=field, v=value: self._apply_field_value_delayed(f, v))
                
            # Cas général: tout autre type de champ
            else:
                field.set_value(value)
        except Exception as e:
            logger.error(f"Erreur lors de l'application de la valeur '{value}' au champ {field_id}: {e}")
    
    def _apply_field_value_delayed(self, field, value, attempts=0, max_attempts=5):
        """Applique une valeur au champ après un délai, avec plusieurs tentatives si nécessaire"""
        try:
            field_id = getattr(field, 'field_id', 'inconnu')
            logger.debug(f"Tentative {attempts+1}/{max_attempts} d'application différée pour {field_id}: '{value}'")
            
            # Si le widget input existe, appliquer la valeur
            if hasattr(field, 'input') and field.input is not None:
                # Pour les champs IP, utiliser set_value
                if hasattr(field, '_pending_value'):
                    logger.debug(f"Utilisation de set_value pour champ IP {field_id}")
                    field.set_value(value)
                # Pour les autres types de champs
                else:
                    logger.debug(f"Application directe à l'input pour {field_id}")
                    old_value = field.input.value
                    if old_value != value:
                        field.input.value = value
                        field.value = value
                logger.debug(f"Valeur appliquée avec succès au champ {field_id}")
                return True
                
            # Si le nombre maximum de tentatives n'est pas atteint, réessayer plus tard
            elif attempts < max_attempts:
                logger.debug(f"Input toujours pas créé pour {field_id}, nouvelle tentative programmée")
                # Augmenter le délai à chaque tentative (100ms, 200ms, 400ms, 800ms, 1600ms)
                delay = 0.1 * (2 ** attempts)
                field.call_later(lambda f=field, v=value, a=attempts: 
                               self._apply_field_value_delayed(f, v, a+1, max_attempts), delay)
            else:
                logger.error(f"Échec d'application après {max_attempts} tentatives pour {field_id}")
                
        except Exception as e:
            logger.error(f"Erreur lors de l'application différée: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Gère les changements d'état des cases à cocher avec suivi spécifique au plugin"""
        # Appeler d'abord l'implémentation parente
        super().on_checkbox_changed(event)

        # Gestion supplémentaire spécifique au plugin
        checkbox_id = event.checkbox.id
        logger.debug(f"Changement d'état de la case à cocher {checkbox_id}")

        for field_id, field in self.fields_by_id.items():
            if hasattr(field, 'source_id') and checkbox_id == f"checkbox_{field.source_id}_{field.field_id}":
                # Stocker dans la collection de champs spécifique au plugin
                self.fields_by_plugin[self.source_id][field_id] = field
                logger.debug(f"Champ {field_id} mis à jour dans la collection de {self.source_id}")
                break