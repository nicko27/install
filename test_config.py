from ui.config import PluginConfig
from textual.app import App

class TestApp(App):
    def on_mount(self):
        # Créer une instance de PluginConfig avec le plugin home_copy
        plugin_screen = PluginConfig([("home_copy", 1)])
        self.push_screen(plugin_screen)

if __name__ == "__main__":
    app = TestApp()
    app.run()
