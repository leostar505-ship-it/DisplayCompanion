import sys
import threading

MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8, "windows": 0x8}
NAMED = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "backspace": 0x08, "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
}
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


def parse(spec):
    parts = [p.strip().lower() for p in str(spec).replace(" ", "").split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    key = None
    for part in parts:
        if part in MODS:
            mods |= MODS[part]
        elif key is not None:
            return None
        elif part in NAMED:
            key = NAMED[part]
        elif len(part) == 1 and part.isalnum():
            key = ord(part.upper())
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            key = 0x70 + int(part[1:]) - 1
        else:
            return None
    if key is None or mods == 0:
        return None
    return mods, key


class Hotkey:
    def __init__(self):
        self.thread = None
        self.thread_id = None
        self.error = ""
        self.spec = ""

    def start(self, spec, callback):
        self.stop()
        parsed = parse(spec)
        if parsed is None:
            self.error = "Use something like ctrl+alt+c (at least one of ctrl, alt, shift, win plus a key)."
            return False
        if sys.platform != "win32":
            self.error = "Global hotkeys only work on Windows."
            return False
        ready = threading.Event()
        result = {}
        self.thread = threading.Thread(target=self._run, args=(parsed, callback, ready, result), daemon=True)
        self.thread.start()
        ready.wait(2.0)
        if not result.get("ok"):
            self.error = result.get("error", "That hotkey is already used by another program.")
            self.thread = None
            return False
        self.error = ""
        self.spec = spec
        return True

    def _run(self, parsed, callback, ready, result):
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self.thread_id = kernel32.GetCurrentThreadId()
        mods, key = parsed
        if not user32.RegisterHotKey(None, 1, mods | MOD_NOREPEAT, key):
            result["ok"] = False
            ready.set()
            return
        result["ok"] = True
        ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                try:
                    callback()
                except Exception:
                    pass
        user32.UnregisterHotKey(None, 1)

    def stop(self):
        if self.thread is not None and self.thread_id is not None and sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
            self.thread.join(1.0)
        self.thread = None
        self.thread_id = None
