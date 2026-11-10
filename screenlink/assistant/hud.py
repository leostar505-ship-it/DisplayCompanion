import sys
import time
import tkinter as tk

from PIL import ImageTk

from . import hudart

SLIDE = 0.24
FADE = 0.26
MARGIN = 24
KEY_HEX = "#010101"


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def make_click_through(window):
    if sys.platform != "win32":
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
        gwl = -20
        style = user32.GetWindowLongW(hwnd, gwl)
        user32.SetWindowLongW(hwnd, gwl, style | 0x80000 | 0x20 | 0x80 | 0x8000000)
    except Exception:
        pass


class Hud:
    def __init__(self, root, scale=1.5, speed=1.6):
        self.root = root
        self.scale = scale
        self.speed = speed
        self.card = None
        self.win = None
        self.label = None
        self.photo = None
        self.state = None
        self.running = False
        self.visible = False
        self.last_geometry = None

    @property
    def eff(self):
        try:
            ui = max(1.0, float(self.root.winfo_fpixels("1i")) / 96.0)
        except Exception:
            ui = 1.0
        return self.scale * ui

    def configure(self, scale, speed):
        speed = max(0.5, speed)
        if abs(scale - self.scale) > 0.01:
            self.scale = scale
            self.card = None
            self._destroy()
        self.speed = speed

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
        if self.card is None:
            self.card = hudart.Card(self.eff)
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

    def show(self, kind, seconds=None, detail=None):
        if not self._ensure():
            return
        now = time.perf_counter()
        active = self.state is not None and self.state["out"] is None
        self.state = {
            "kind": kind,
            "start": self.state["start"] if active else now,
            "changed": now,
            "seconds": seconds,
            "detail": detail,
            "out": None,
        }
        if not self.running:
            self.running = True
            self._frame()

    def hide(self):
        if self.state is not None and self.state["out"] is None:
            self.state["out"] = time.perf_counter()

    def hide_now(self):
        self.state = None
        if self.win is not None:
            self.win.withdraw()
        self.visible = False

    def is_showing(self):
        return self.state is not None

    def current_kind(self):
        return self.state["kind"] if self.state else None

    def _frame(self):
        s = self.state
        if s is None or self.win is None:
            self.running = False
            if self.win is not None:
                self.win.withdraw()
            self.visible = False
            return
        now = time.perf_counter()
        if s["seconds"] is not None and s["out"] is None and now - s["changed"] >= s["seconds"]:
            s["out"] = now
        slide = ease((now - s["start"]) / SLIDE)
        alpha = slide
        if s["out"] is not None:
            fade = (now - s["out"]) / FADE
            alpha = min(slide, max(0.0, 1 - fade))
            if fade >= 1:
                self.state = None
                self.running = False
                self.win.withdraw()
                self.visible = False
                return
        frac = None
        if s["seconds"] is not None and s["out"] is None:
            frac = max(0.0, 1 - (now - s["changed"]) / s["seconds"])
        t = now - s["changed"]
        detail = s.get("detail")
        img = self.card.render(s["kind"], t, now, frac, self.speed,
                               title=detail[0] if detail else None, sub=detail[1] if detail else None)
        self.photo = ImageTk.PhotoImage(img)
        self.label.configure(image=self.photo)
        try:
            sw = self.win.winfo_screenwidth()
            x = int(sw - self.card.w - MARGIN * self.eff + (1 - slide) * 40 * self.eff)
            y = int(MARGIN * self.eff)
            geometry = "%dx%d+%d+%d" % (self.card.w, self.card.h, x, y)
            if geometry != self.last_geometry:
                self.win.geometry(geometry)
                self.last_geometry = geometry
            try:
                self.win.attributes("-alpha", max(0.01, 0.97 * alpha))
            except tk.TclError:
                pass
            if not self.visible:
                self.win.deiconify()
                self.win.attributes("-topmost", True)
                self.visible = True
        except tk.TclError:
            self.running = False
            return
        self.root.after(16, self._frame)

    def close(self):
        self.state = None
        self.running = False
        self._destroy()
