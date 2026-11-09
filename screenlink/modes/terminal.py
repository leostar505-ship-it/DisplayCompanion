import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw

from .. import fonts
from ..display import H, W
from ..widgets import ColorField, Slider
from .base import Mode


class TerminalMode(Mode):
    name = "Terminal"
    blurb = "Type a line, press Enter, it scrolls up on the screen"

    def __init__(self, app):
        super().__init__(app)
        self.lines = []
        self.font_paths = fonts.discover_fonts()

    def build(self, parent):
        f = ttk.Frame(parent)
        self.frame = f
        mono = next((n for n in ("DejaVu Sans Mono", "Consolas", "Liberation Mono") if n in self.font_paths),
                    fonts.BUILTIN)
        self.font_var = tk.StringVar(value=mono)
        self.entry_var = tk.StringVar()

        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky="n", padx=(0, 24))
        ttk.Label(left, text="Type here and press Enter", style="Muted.TLabel").pack(anchor="w")
        row = ttk.Frame(left)
        row.pack(anchor="w", pady=4)
        self.entry = ttk.Entry(row, textvariable=self.entry_var, width=44)
        self.entry.pack(side="left")
        self.entry.bind("<Return>", lambda e: self.submit())
        ttk.Button(row, text="Send line", style="Accent.TButton", command=self.submit).pack(side="left", padx=6)
        ttk.Button(row, text="Clear screen", command=self.clear).pack(side="left")

        right = ttk.Frame(f)
        right.grid(row=0, column=1, sticky="n")
        row = ttk.Frame(right)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Font", width=14).pack(side="left")
        cb = ttk.Combobox(row, textvariable=self.font_var, values=list(self.font_paths), state="readonly", width=20)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.redraw())
        self.size = Slider(right, "Size (px)", 6, 24, 10, command=self.redraw, integer=True)
        self.size.pack(anchor="w", pady=2)
        self.fg = ColorField(right, "Text colour", "#33ff66", command=self.redraw)
        self.fg.pack(anchor="w", pady=2)
        self.bg = ColorField(right, "Background", "#000000", command=self.redraw)
        self.bg.pack(anchor="w", pady=2)
        return f

    def activate(self):
        self.redraw()
        self.entry.focus_set()

    def submit(self):
        text = self.entry_var.get()
        self.entry_var.set("")
        self.lines.extend(text.split("\n"))
        self.lines = self.lines[-300:]
        self.redraw()

    def clear(self):
        self.lines = []
        self.redraw()

    def redraw(self, *_):
        path = self.font_paths.get(self.font_var.get())
        font = fonts.load_font(path, self.size.get())
        wrapped = []
        for line in self.lines:
            wrapped.extend(fonts.wrap_text(line, font, W - 4))
        probe = ImageDraw.Draw(Image.new("RGB", (4, 4)))
        box = probe.textbbox((0, 0), "Ag", font=font)
        line_h = max(1, box[3] - box[1] + 2)
        rows = max(1, (H - 2) // line_h)
        shown = wrapped[-rows:]
        img = Image.new("RGB", (W, H), self.bg.get())
        draw = ImageDraw.Draw(img)
        y = 2
        for line in shown:
            draw.text((2, y - box[1]), line, fill=self.fg.get(), font=font)
            y += line_h
        self.display.full_image(img)
        self.display.flush()
