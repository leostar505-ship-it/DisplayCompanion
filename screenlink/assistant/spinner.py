import math
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from .hud import KEY_HEX, MARGIN, make_click_through

SIZE = 64
BG = (28, 28, 36)
ACCENT = (240, 128, 64)
FADE = 0.25
SPIN_RATE = 140.0
STOP_TIME = 0.55
PETALS = (1.0, 0.72, 0.94, 0.66, 1.0, 0.74, 0.9, 0.68)


def render(angle, size):
    ss = 4
    big = size * ss
    img = Image.new("RGB", (big, big), (1, 1, 1))
    d = ImageDraw.Draw(img)
    c = big / 2.0
    d.ellipse((0, 0, big - 1, big - 1), fill=BG)
    n = len(PETALS)
    for i, length in enumerate(PETALS):
        a = math.radians(angle + i * 360.0 / n)
        r0 = big * 0.07
        r1 = big * (0.2 + 0.22 * length)
        w = big * 0.052
        x0, y0 = c + math.cos(a) * r0, c + math.sin(a) * r0
        x1, y1 = c + math.cos(a) * r1, c + math.sin(a) * r1
        d.line((x0, y0, x1, y1), fill=ACCENT, width=int(w * 2))
        for x, y in ((x0, y0), (x1, y1)):
            d.ellipse((x - w, y - w, x + w, y + w), fill=ACCENT)
    d.ellipse((c - big * 0.045, c - big * 0.045, c + big * 0.045, c + big * 0.045), fill=ACCENT)
    return img.resize((size, size), Image.LANCZOS)


class Spinner:
    def __init__(self, root, scale=1.5):
        self.root = root
        self.scale = scale
        self.win = None
        self.label = None
        self.photo = None
        self.state = "hide"
        self.angle = 0.0
        self.rate = 0.0
        self.running = False
        self.visible = False
        self.alpha = 0.0
        self.hide_at = None
        self.last = 0.0
        self.last_geometry = None

    @property
    def eff(self):
        try:
            ui = max(1.0, float(self.root.winfo_fpixels("1i")) / 96.0)
        except Exception:
            ui = 1.0
        return self.scale * ui

    def configure(self, scale):
        if abs(scale - self.scale) > 0.01:
            self.scale = scale
            self._destroy()

    def _destroy(self):
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
        self.win = None
        self.label = None
        self.visible = False
        self.last_geometry = None

    def _ensure(self):
        if self.win is not None:
            return True
        try:
            win = tk.Toplevel(self.root)
            win.withdraw()
            win.overrideredirect(True)
            win.configure(bg=KEY_HEX)
            win.attributes("-topmost", True)
            try:
                win.attributes("-transparentcolor", KEY_HEX)
            except tk.TclError:
                pass
            label = tk.Label(win, bd=0, highlightthickness=0, bg=KEY_HEX)
            label.pack()
            self.win = win
            self.label = label
            win.update_idletasks()
            make_click_through(win)
            return True
        except tk.TclError:
            self.win = None
            return False

    def set(self, state, hide_after=None):
        if state == "hide":
            self.state = "hide"
            self.hide_at = None
            if not self.running and self.win is not None:
                self.win.withdraw()
                self.visible = False
            return
        if not self._ensure():
            return
        self.state = state
        self.hide_at = time.perf_counter() + hide_after if hide_after else None
        if not self.running:
            self.running = True
            self.last = time.perf_counter()
            self._frame()

    def hide_now(self):
        self.state = "hide"
        self.hide_at = None
        self.alpha = 0.0
        self.rate = 0.0
        self.running = False
        if self.win is not None:
            self.win.withdraw()
        self.visible = False

    def is_spinning(self):
        return self.state == "spin"

    def _frame(self):
        if self.win is None:
            self.running = False
            return
        now = time.perf_counter()
        dt = min(0.1, max(0.0, now - self.last))
        self.last = now
        if self.hide_at is not None and now >= self.hide_at and self.state != "hide":
            self.state = "hide"
        if self.state == "spin":
            self.rate = SPIN_RATE
        else:
            self.rate = max(0.0, self.rate - SPIN_RATE / STOP_TIME * dt)
        self.angle = (self.angle + self.rate * dt) % 360.0
        target = 0.0 if self.state == "hide" else 1.0
        step = dt / FADE
        self.alpha = min(target, self.alpha + step) if target > self.alpha else max(target, self.alpha - step)
        if self.state == "hide" and self.alpha <= 0.0:
            self.running = False
            self.win.withdraw()
            self.visible = False
            return
        size = max(24, int(SIZE * self.eff))
        self.photo = ImageTk.PhotoImage(render(self.angle, size))
        self.label.configure(image=self.photo)
        try:
            geometry = "%dx%d+%d+%d" % (size, size, int(MARGIN * self.eff), int(MARGIN * self.eff))
            if geometry != self.last_geometry:
                self.win.geometry(geometry)
                self.last_geometry = geometry
            self.win.attributes("-alpha", max(0.01, 0.97 * self.alpha))
            if not self.visible:
                self.win.deiconify()
                self.win.attributes("-topmost", True)
                self.visible = True
        except tk.TclError:
            self.running = False
            return
        self.root.after(33, self._frame)

    def close(self):
        self.running = False
        self.state = "hide"
        self._destroy()
