import tkinter as tk
from tkinter import filedialog, ttk

from .. import fonts
from ..display import H, W
from ..widgets import ColorField, Slider
from .base import Mode

DEBOUNCE = 0.12


class TextMode(Mode):
    name = "Text"
    blurb = "Show any text, with any font, optionally scrolling"

    def __init__(self, app):
        super().__init__(app)
        self.font_paths = fonts.discover_fonts()
        self.dirty = True
        self.quiet = 0.0
        self.strip = None
        self.strip_w = 0
        self.offset = 0.0
        self.sent_offset = -1

    def build(self, parent):
        f = ttk.Frame(parent)
        self.frame = f
        names = list(self.font_paths)
        default = "DejaVu Sans" if "DejaVu Sans" in self.font_paths else ("Segoe UI" if "Segoe UI" in self.font_paths else fonts.BUILTIN)
        self.font_var = tk.StringVar(value=default)
        self.align_var = tk.StringVar(value="center")
        self.valign_var = tk.StringVar(value="middle")
        self.scroll_var = tk.BooleanVar(value=False)
        self.auto_var = tk.BooleanVar(value=False)

        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky="n", padx=(0, 24))
        ttk.Label(left, text="Text to show", style="Muted.TLabel").pack(anchor="w")
        self.box = tk.Text(left, width=34, height=5, bg="#22222e", fg="#e8e8f0", insertbackground="#e8e8f0",
                           relief="flat", font=("TkDefaultFont", 11), wrap="word")
        self.box.pack(anchor="w", pady=4)
        self.box.insert("1.0", "Hello Leo!")
        self.box.bind("<KeyRelease>", lambda e: self._mark())

        mid = ttk.Frame(f)
        mid.grid(row=0, column=1, sticky="n", padx=(0, 24))
        row = ttk.Frame(mid)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Font", width=14).pack(side="left")
        cb = ttk.Combobox(row, textvariable=self.font_var, values=names, state="readonly", width=20)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._mark())
        ttk.Button(row, text="Browse...", command=self._browse).pack(side="left", padx=6)
        self.size = Slider(mid, "Size (px)", 6, 72, 18, command=self._mark, integer=True)
        self.size.pack(anchor="w", pady=2)
        ttk.Checkbutton(mid, text="Auto-fit size to screen", variable=self.auto_var, command=self._mark).pack(
            anchor="w", pady=2)
        self.fg = ColorField(mid, "Text colour", "#ffffff", command=self._mark)
        self.fg.pack(anchor="w", pady=2)
        self.bg = ColorField(mid, "Background", "#000000", command=self._mark)
        self.bg.pack(anchor="w", pady=2)

        right = ttk.Frame(f)
        right.grid(row=0, column=2, sticky="n")
        row = ttk.Frame(right)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Align", width=10).pack(side="left")
        for v in ("left", "center", "right"):
            ttk.Radiobutton(row, text=v, value=v, variable=self.align_var, command=self._mark).pack(side="left", padx=3)
        row = ttk.Frame(right)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Vertical", width=10).pack(side="left")
        for v in ("top", "middle", "bottom"):
            ttk.Radiobutton(row, text=v, value=v, variable=self.valign_var, command=self._mark).pack(side="left", padx=3)
        ttk.Checkbutton(right, text="Scroll sideways (one line)", variable=self.scroll_var,
                        command=self._mark).pack(anchor="w", pady=6)
        self.speed = Slider(right, "Scroll speed", 10, 200, 60, fmt="{:.0f} px/s")
        self.speed.pack(anchor="w", pady=2)
        return f

    def _browse(self):
        path = filedialog.askopenfilename(filetypes=[("Fonts", "*.ttf *.otf *.ttc")])
        if path:
            name = path.replace("\\", "/").split("/")[-1]
            self.font_paths[name] = path
            self.font_var.set(name)
            self._mark()

    def _mark(self, *_):
        self.dirty = True
        self.quiet = 0.0

    def activate(self):
        self._mark()

    def _text(self):
        return self.box.get("1.0", "end-1c")

    def _font(self, text):
        path = self.font_paths.get(self.font_var.get())
        size = fonts.fit_size(text, path) if self.auto_var.get() and not self.scroll_var.get() else self.size.get()
        return fonts.load_font(path, size)

    def _render_static(self):
        text = self._text()
        img = fonts.render_block(text, self._font(text), self.fg.get(), self.bg.get(),
                                 self.align_var.get(), self.valign_var.get())
        self.display.full_image(img)
        self.display.flush()

    def _prepare_strip(self):
        text = " ".join(self._text().split())
        self.strip, self.strip_w = fonts.render_strip(text or " ", self._font(text), self.fg.get(), self.bg.get())
        self.offset = 0.0
        self.sent_offset = -1

    def tick(self, dt):
        self.quiet += dt
        if self.dirty and self.quiet >= DEBOUNCE:
            self.dirty = False
            if self.scroll_var.get():
                self._prepare_strip()
            else:
                self.strip = None
                self._render_static()
        if self.scroll_var.get() and self.strip is not None:
            span = self.strip_w + W
            self.offset = (self.offset + self.speed.get() * dt) % span
            pos = int(self.offset)
            if pos != self.sent_offset:
                self.sent_offset = pos
                crop = self.strip.crop((pos, 0, pos + W, H))
                self.display.full_image(crop)
                self.display.flush(realtime=True)
