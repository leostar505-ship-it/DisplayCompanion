import tkinter as tk
from tkinter import filedialog, ttk

from PIL import Image, ImageEnhance, ImageSequence

from ..display import H, W
from ..widgets import ColorField, Slider
from .base import Mode

FIT_MODES = ("Fit (keep shape)", "Fill (crop)", "Stretch")


def fit_image(img, mode, bg):
    img = img.convert("RGB")
    iw, ih = img.size
    if mode.startswith("Stretch"):
        return img.resize((W, H), Image.LANCZOS)
    if mode.startswith("Fill"):
        scale = max(W / iw, H / ih)
    else:
        scale = min(W / iw, H / ih)
    nw = max(1, int(round(iw * scale)))
    nh = max(1, int(round(ih * scale)))
    resized = img.resize((nw, nh), Image.LANCZOS)
    out = Image.new("RGB", (W, H), bg)
    out.paste(resized, ((W - nw) // 2, (H - nh) // 2))
    return out


class ImageMode(Mode):
    name = "Image"
    blurb = "Show a picture or play an animated GIF"

    def __init__(self, app):
        super().__init__(app)
        self.originals = []
        self.durations = []
        self.frames = []
        self.index = 0
        self.elapsed = 0.0
        self.dirty = False
        self.path = ""

    def build(self, parent):
        f = ttk.Frame(parent)
        self.frame = f
        self.fit_var = tk.StringVar(value=FIT_MODES[0])
        self.loop_var = tk.BooleanVar(value=True)

        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky="n", padx=(0, 24))
        ttk.Button(left, text="Open image or GIF...", style="Accent.TButton", command=self.open_file).pack(
            anchor="w", pady=4)
        self.file_label = ttk.Label(left, text="No file loaded", style="Muted.TLabel", wraplength=280)
        self.file_label.pack(anchor="w", pady=4)
        row = ttk.Frame(left)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Scaling", width=14).pack(side="left")
        cb = ttk.Combobox(row, textvariable=self.fit_var, values=FIT_MODES, state="readonly", width=18)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._reprocess())

        right = ttk.Frame(f)
        right.grid(row=0, column=1, sticky="n")
        self.bg = ColorField(right, "Letterbox", "#000000", command=self._reprocess)
        self.bg.pack(anchor="w", pady=2)
        self.bright = Slider(right, "Brightness", 0.2, 2.0, 1.0, command=self._reprocess)
        self.bright.pack(anchor="w", pady=2)
        self.contrast = Slider(right, "Contrast", 0.2, 2.0, 1.0, command=self._reprocess)
        self.contrast.pack(anchor="w", pady=2)
        ttk.Checkbutton(right, text="Loop animation", variable=self.loop_var).pack(anchor="w", pady=2)
        return f

    def open_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("All files", "*.*")])
        if path:
            self.load(path)

    def load(self, path):
        try:
            img = Image.open(path)
            self.originals = []
            self.durations = []
            for frame in ImageSequence.Iterator(img):
                self.originals.append(frame.convert("RGB"))
                self.durations.append(max(0.02, float(frame.info.get("duration", 100)) / 1000.0))
        except Exception as exc:
            self.file_label.configure(text="Could not open: %s" % exc)
            return False
        self.path = path
        self.file_label.configure(text="%s\n%d frame(s)" % (path.replace("\\", "/").split("/")[-1],
                                                           len(self.originals)))
        self._reprocess()
        return True

    def _reprocess(self, *_):
        self.frames = []
        for frame in self.originals:
            out = fit_image(frame, self.fit_var.get(), self.bg.get())
            if abs(self.bright.get() - 1.0) > 0.01:
                out = ImageEnhance.Brightness(out).enhance(self.bright.get())
            if abs(self.contrast.get() - 1.0) > 0.01:
                out = ImageEnhance.Contrast(out).enhance(self.contrast.get())
            self.frames.append(out)
        self.index = 0
        self.elapsed = 0.0
        self.dirty = True

    def activate(self):
        self.dirty = bool(self.frames)

    def tick(self, dt):
        if not self.frames:
            return
        if len(self.frames) == 1:
            if self.dirty:
                self.dirty = False
                self.display.full_image(self.frames[0])
                self.display.flush()
            return
        advance = self.dirty
        if self.dirty:
            self.dirty = False
        else:
            self.elapsed += dt
            if self.elapsed >= self.durations[self.index]:
                self.elapsed = 0.0
                nxt = self.index + 1
                if nxt >= len(self.frames):
                    if not self.loop_var.get():
                        return
                    nxt = 0
                self.index = nxt
                advance = True
        if advance:
            self.display.full_image(self.frames[self.index])
            self.display.flush(realtime=True)
