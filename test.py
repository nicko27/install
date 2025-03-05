from textual.app import App
from textual.widgets import Header, Footer, Button, Static
from textual.containers import Container

class SimpleApp(App):
    CSS = """
    Screen {
        align: center middle;
    }
    
    Button {
        width: 50%;
    }
    """

    def compose(self):
        yield Header()
        yield Container(Button("Hello, World!"))
        yield Footer()

if __name__ == "__main__":
    app = SimpleApp()
    app.run()
