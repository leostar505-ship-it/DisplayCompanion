from tkinter import ttk


class Mode:
    name = ""
    blurb = ""

    def __init__(self, app):
        self.app = app
        self.display = app.display
        self.frame = None

    def build(self, parent):
        self.frame = ttk.Frame(parent)
        return self.frame

    def activate(self):
        pass

    def deactivate(self):
        pass

    def tick(self, dt):
        pass

    def mouse(self, kind, x, y):
        pass

    def on_reply(self, text):
        pass

    def on_link_change(self):
        pass
