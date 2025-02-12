#!/usr/bin/env python3
from textual.app import App
from ui.execution import ExecutionScreen

class TestApp(App):
    def on_mount(self) -> None:
        # Configuration des plugins de test
        plugins_config = {
            'python_progress_test_1': {
                'test_name': 'PythonTest1',
                'test_complexity': 'simple'
            },
            'python_progress_test_2': {
                'test_name': 'PythonTest2',
                'test_complexity': 'moderate'
            }
        }
        
        # Afficher l'écran d'exécution
        self.push_screen(ExecutionScreen(plugins_config))

if __name__ == "__main__":
    app = TestApp()
    app.run()
