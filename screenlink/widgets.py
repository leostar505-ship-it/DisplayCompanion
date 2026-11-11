import tkinter as tk
from tkinter import colorchooser, ttk

from . import colors

BG = "#0e0e15"
PANEL = "#15151d"
FIELD = "#22222e"
LINE = "#33334a"
TEXT = "#e8e8f0"
MUTED = "#99a0b0"
ACCENT = "#7a62ff"


UI = 1.0


def apply_style(root, ui=1.0):
    global UI
    UI = ui
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=PANEL, foreground=TEXT, fieldbackground=FIELD, bordercolor=LINE,
                    lightcolor=PANEL, darkcolor=PANEL, troughcolor=FIELD, focuscolor=PANEL)
    style.configure("TFrame", background=PANEL)
    style.configure("Dark.TFrame", background=BG)
    style.configure("TLabel", background=PANEL, foreground=TEXT)
    style.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
    style.configure("TButton", background=FIELD, foreground=TEXT, padding=(int(10 * ui), int(5 * ui)), borderwidth=1)
    style.map("TButton", background=[("active", LINE), ("pressed", ACCENT)])
    style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff")
    style.map("Accent.TButton", background=[("active", "#9582ff")])
    style.configure("TCheckbutton", background=PANEL, foreground=TEXT)
    style.map("TCheckbutton", background=[("active", PANEL)])
    style.configure("TRadiobutton", background=PANEL, foreground=TEXT)
    style.map("TRadiobutton", background=[("active", PANEL)])
    style.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=TEXT, arrowcolor=TEXT)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", TEXT)])
    style.configure("TEntry", fieldbackground=FIELD, foreground=TEXT, insertcolor=TEXT)
    style.configure("Horizontal.TScale", background=PANEL)
    style.configure("TLabelframe", background=PANEL, bordercolor=LINE)
    style.configure("TLabelframe.Label", background=PANEL, foreground=MUTED)
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)


class Slider(ttk.Frame):
    def __init__(self, parent, label, lo, hi, value, command=None, fmt="{:.2f}", length=150, integer=False,
                 label_width=14):
        super().__init__(parent)
        self.integer = integer
        self.fmt = fmt if callable(fmt) else ("{:d}" if integer else fmt)
        self.command = command
        self.var = tk.DoubleVar(value=value)
        ttk.Label(self, text=label, width=label_width).grid(row=0, column=0, sticky="w")
        self.scale = ttk.Scale(self, from_=lo, to=hi, variable=self.var, command=self._changed, length=int(length * UI))
        self.scale.grid(row=0, column=1, padx=6)
        self.value_label = ttk.Label(self, width=11, style="Muted.TLabel")
        self.value_label.grid(row=0, column=2, sticky="w")
        self._refresh()

    def _refresh(self):
        self.value_label.configure(text=self.fmt(self.get()) if callable(self.fmt) else self.fmt.format(self.get()))

    def _changed(self, _value=None):
        self._refresh()
        if self.command:
            self.command()

    def get(self):
        v = float(self.var.get())
        return int(round(v)) if self.integer else v

    def set(self, value):
        self.var.set(value)
        self._refresh()


class ColorField(ttk.Frame):
    def __init__(self, parent, label, value="#ffffff", command=None):
        super().__init__(parent)
        self.command = command
        self.rgb = colors.parse_hex(value) or (255, 255, 255)
        self.var = tk.StringVar(value=colors.to_hex(self.rgb))
        if label:
            ttk.Label(self, text=label, width=14).pack(side="left")
        self.swatch = tk.Button(self, width=3, relief="flat", bd=1, command=self.pick, bg=colors.to_hex(self.rgb),
                                activebackground=colors.to_hex(self.rgb), highlightthickness=0)
        self.swatch.pack(side="left", padx=(0, 6))
        self.entry = ttk.Entry(self, textvariable=self.var, width=9)
        self.entry.pack(side="left")
        self.entry.bind("<KeyRelease>", self._typed)
        self.entry.bind("<FocusOut>", self._typed)

    def _apply(self, rgb):
        self.rgb = rgb
        hexv = colors.to_hex(rgb)
        self.swatch.configure(bg=hexv, activebackground=hexv)
        if self.command:
            self.command()

    def _typed(self, _event=None):
        rgb = colors.parse_hex(self.var.get())
        if rgb is not None:
            self._apply(rgb)

    def pick(self):
        chosen = colorchooser.askcolor(color=colors.to_hex(self.rgb), parent=self)
        if chosen and chosen[1]:
            self.set(colors.parse_hex(chosen[1]))

    def set(self, rgb):
        self.var.set(colors.to_hex(rgb))
        self._apply(tuple(rgb))

    def get(self):
        return self.rgb
