"""
Écran d'exécution des plugins.
"""

import os
import asyncio
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button
from textual.message import Message

from .execution_widget import ExecutionWidget

class ExecutionScreen(Screen):
    """Écran contenant le widget d'exécution des plugins"""

    # Définir les raccourcis clavier, notamment ESC pour quitter
    BINDINGS = [
        ("escape", "quit", "Quitter"),
    ]

    CSS_PATH = os.path.join(os.path.dirname(__file__), "../styles/execution.tcss")
    

    def __init__(self, plugins_config: dict = None, auto_execute: bool = False, report_manager=None):
        """Initialise l'écran avec la configuration des plugins
        
        Args:
            plugins_config: Dictionnaire de configuration des plugins
            auto_execute: Si True, lance l'exécution automatiquement
        """
        super().__init__()
        self.plugins_config = plugins_config
        self.auto_execute = auto_execute
        
    async def on_mount(self) -> None:
        """Appelé quand l'écran est monté"""
        try:
            from ..utils.logging import get_logger
            logger = get_logger('execution_screen')
            logger.debug("Montée de l'écran d'exécution")
            
            # Au lieu d'utiliser call_after_refresh, créer une tâche asynchrone
            # avec un délai pour permettre à l'interface de s'afficher complètement
            self._init_task = asyncio.create_task(self._delayed_initialization())
        except Exception as e:
            from ..utils.logging import get_logger
            logger = get_logger('execution_screen')
            logger.error(f"Erreur lors du montage de l'écran d'exécution: {str(e)}")
            self.notify(f"Erreur lors de l'initialisation: {str(e)}", severity="error")
    
    async def _delayed_initialization(self):
        """Initialisation différée pour permettre à l'interface de s'afficher"""
        try:
            from ..utils.logging import get_logger
            logger = get_logger('execution_screen')
            
            # Attendre que l'interface soit complètement affichée
            logger.debug("Attente pour permettre à l'interface de s'afficher complètement")
            await asyncio.sleep(1.0)  # 1 seconde de délai
            
            # Vérifier que l'écran est toujours monté
            if not self.is_mounted:
                logger.debug("L'écran n'est plus monté, annulation de l'initialisation")
                return
                
            # Maintenant initialiser l'écran
            logger.debug("Début de l'initialisation de l'écran après délai")
            await self.initialize_screen()
        except Exception as e:
            logger.error(f"Erreur dans l'initialisation différée: {str(e)}")
            self.notify(f"Erreur lors de l'initialisation: {str(e)}", severity="error")
    
    async def initialize_screen(self):
        """Initialise l'écran après le montage complet"""
        try:
            from ..utils.logging import get_logger
            logger = get_logger('execution_screen')
            
            # Récupérer le widget d'exécution
            widget = self.query_one(ExecutionWidget)
                
            if self.auto_execute:
                # En mode auto, masquer les boutons Démarrer et Retour définitivement
                try:
                    start_button = widget.query_one("#start-button")
                    back_button = widget.query_one("#back-button")
                    if start_button and back_button:
                        start_button.add_class("hidden")
                        back_button.add_class("hidden")
                        logger.debug("Boutons Démarrer et Retour masqués en mode auto")
                except Exception as e:
                    logger.error(f"Erreur lors du masquage des boutons en mode auto: {str(e)}")
                
                # Lancer l'exécution automatiquement (le délai a déjà été appliqué dans _delayed_initialization)
                if widget:
                    
                    # Forcer un rafraîchissement de l'interface avant de commencer
                    logger.debug("Forçage d'un rafraîchissement de l'interface avant l'exécution automatique")
                    # Utiliser refresh() sans await car ce n'est pas une méthode asynchrone
                    self.refresh()
                    
                    # Attendre un délai plus long pour s'assurer que l'interface est complètement chargée
                    logger.debug("Attente d'un délai de 0.5 secondes pour garantir le chargement complet de l'interface")
                    await asyncio.sleep(0.5)
                    
                    # Vérifier que l'écran est toujours monté
                    if not self.is_mounted:
                        logger.debug("L'écran n'est plus monté, annulation de l'exécution automatique")
                        return
                    
                    # Forcer un second rafraîchissement pour garantir que tous les éléments sont visibles
                    self.refresh()
                    await asyncio.sleep(0.1)
                        
                    # Démarrer l'exécution
                    logger.debug("Démarrage de l'exécution automatique")
                    self._execution_running = True
                    
                    try:
                        # Exécuter directement plutôt que via une tâche pour éviter les problèmes de troncature
                        logger.debug("Démarrage direct de l'exécution")
                        # En mode auto, ne pas réafficher les boutons après l'exécution
                        await widget.start_execution(auto_mode=True)
                        logger.debug("Exécution terminée avec succès")
                    except asyncio.CancelledError:
                        logger.info("Exécution automatique annulée par l'utilisateur")
                        self.notify("Exécution annulée", severity="warning")
                    except Exception as e:
                        logger.error(f"Erreur pendant l'exécution: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        self.notify(f"Erreur: {str(e)}", severity="error")
                    finally:
                        # S'assurer que le flag d'exécution est remis à False
                        self._execution_running = False
        except Exception as e:
            from ..utils.logging import get_logger
            logger = get_logger('execution_screen')
            logger.error(f"Erreur lors de l'initialisation de l'écran: {str(e)}")
            self.notify(f"Erreur lors de l'initialisation: {str(e)}", severity="error")
    
    def action_quit(self) -> None:
        """Action exécutée lorsque l'utilisateur appuie sur ESC"""
        from ..utils.logging import get_logger
        logger = get_logger('execution_screen')
        
        try:
            logger.info("Demande de sortie via touche ESC")
            
            # Vérifier si une exécution est en cours
            if hasattr(self, '_execution_running') and self._execution_running:
                logger.info("Exécution en cours détectée, lancement de la procédure d'annulation")
                
                # Arrêter l'exécution en cours
                if hasattr(self, '_execution_task') and self._execution_task:
                    try:
                        logger.info("Annulation de la tâche d'exécution en cours")
                        self._execution_task.cancel()
                    except Exception as e:
                        logger.warning(f"Erreur lors de l'annulation de la tâche: {e}")
                
                # Arrêter également l'exécution dans le widget si possible
                try:
                    widget = self.query_one(ExecutionWidget)
                    if hasattr(widget, 'is_running'):
                        logger.info("Arrêt de l'exécution dans le widget")
                        widget.is_running = False
                except Exception as e:
                    logger.warning(f"Impossible d'arrêter l'exécution dans le widget: {e}")
                
                # Lancer la procédure d'annulation asynchrone
                asyncio.create_task(self._handle_cancellation())
                # Notifier l'utilisateur
                self.notify("Annulation de l'exécution en cours...", severity="warning")
                return  # Ne pas quitter immédiatement, laisser le temps à la tâche de se terminer
                
            self.app.exit()

            
        except Exception as e:
            logger.error(f"Erreur lors de la sortie: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            self.notify(f"Erreur lors de la sortie: {str(e)}", severity="error")
            # Tenter de quitter l'écran même en cas d'erreur
            try:
                self.app.pop_screen()
            except Exception:
                pass
    
    async def on_execution_completed(self) -> None:
        """Appelé quand l'exécution des plugins est terminée"""
        pass
                
    async def _handle_cancellation(self):
        """Gère l'annulation de l'exécution et quitte l'écran après un court délai"""
        from ..utils.logging import get_logger
        logger = get_logger('execution_screen')
        
        try:
            # Marquer l'exécution comme terminée
            self._execution_running = False
            
            # Arrêter tous les plugins en cours si possible
            try:
                widget = self.query_one(ExecutionWidget)
                if hasattr(widget, 'is_running'):
                    logger.info("Arrêt forcé des plugins en cours d'exécution")
                    widget.is_running = False
            except Exception as e:
                logger.warning(f"Impossible d'arrêter les plugins en cours: {e}")
            
            # Attendre un délai plus long pour que l'annulation prenne effet
            # et que l'interface puisse se mettre à jour
            logger.debug("Attente de 1 seconde pour permettre l'arrêt complet de l'exécution")
            await asyncio.sleep(1.0)
            
            # Vérifier que l'écran est toujours monté
            if not self.is_mounted:
                logger.debug("L'écran n'est plus monté, annulation de la fermeture")
                return
            
            # Quitter l'écran ou l'application selon le contexte
            if hasattr(self, 'auto_execute') and self.auto_execute:
                logger.info("Mode auto détecté, fermeture de l'application après annulation")
                self.app.exit()
            else:
                logger.info("Annulation de l'exécution terminée, retour à l'écran précédent")
                self.app.pop_screen()
        except Exception as e:
            logger.error(f"Erreur lors de la gestion de l'annulation: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Tenter de quitter l'écran même en cas d'erreur
            try:
                self.app.pop_screen()
            except Exception:
                pass

    def compose(self) -> ComposeResult:
        """Création de l'interface"""
        try:
            yield ExecutionWidget(self.plugins_config)
        except Exception as e:
            from ..utils.logging import get_logger
            logger = get_logger('execution_screen')
            logger.error(f"Erreur lors de la composition de l'écran d'exécution: {str(e)}")
            # Fallback to a basic message if widget creation fails
            from textual.widgets import Static
            yield Static(f"Erreur lors de la création de l'interface: {str(e)}\n\nVeuillez vérifier les logs pour plus de détails.")