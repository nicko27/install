from ui.choice import Choice
from ui.utils import setup_logging

if __name__ == "__main__":
    # Initialiser le logging
    logger = setup_logging()
    
    # Démarrer l'application
    app = Choice()
    app.run()