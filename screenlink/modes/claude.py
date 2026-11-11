import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

import numpy as np
from PIL import Image

from .. import fonts
from ..assistant import api, blaze, claude_code, cues, hotkey, screenshot, smartshot, speech, voice, whispercpp
from ..assistant.hud import Hud
from ..assistant.spinner import starburst
from ..assistant.settings import Settings
from ..assistant.typer import TypeSchedule, capacity, fit_reply
from ..widgets import ACCENT, FIELD, PANEL, TEXT, Slider
from .base import Mode

MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5")
LISTEN_GIVE_UP = 40.0
FG = (255, 255, 255)
BG = (0, 0, 0)
DIM = (150, 156, 170)
BAD = (255, 90, 100)


ICON = 16
SETTLE = 0.7
NEUTRAL = 45.0
NOTCH = (ICON + 5, ICON + 4)

ERROR_CODES = (
    ("voice model", "E1", "No voice model"),
    ("didn't hear", "E2", "Heard nothing"),
    ("didn't catch", "E3", "Didn't catch it"),
    ("was not found", "E4", "No Claude Code"),
    ("no api key", "E5", "No API key"),
    ("screenshot", "E6", "Shot failed"),
    ("not signed in", "E7", "Not signed in"),
    ("too long", "E8", "Timed out"),
    ("claude code failed", "E9", "Claude failed"),
    ("could not start", "E10", "Won't start"),
    ("could not reach", "E12", "Network error"),
    ("claude sent", "E11", "API error"),
    ("api", "E11", "API error"),
)


def error_info(message):
    low = str(message).lower()
    for needle, code, short in ERROR_CODES:
        if needle in low:
            return code, short
    return "E0", "Unknown error"


class ClaudeMode(Mode):
    name = "Claude"
    blurb = "Ask Claude by voice, hotkey or keyboard. Replies type onto the screen"

    def __init__(self, app):
        super().__init__(app)
        self.settings = getattr(app, "assistant_settings", None) or Settings()
        self.font_paths = fonts.discover_fonts()
        self.events = queue.Queue()
        self.hotkey = hotkey.Hotkey()
        self.listener = None
        self.hud = None
        self.history = []
        self.phase = "idle"
        self.active = False
        self.question = ""
        self.pending_reply = None
        self.pending_error = None
        self.shot_until = 0.0
        self.listen_since = 0.0
        self.schedule = None
        self.type_start = 0.0
        self.reply_text = ""
        self.shown_key = None
        self.last_img = None
        self.want_send = False
        self.run_ctx = None
        self.board_caption = None
        self.spin_t0 = 0.0
        self.spin_bucket = -1
        self.frozen_angle = 0.0
        self.stop_from = 0.0
        self.stop_to = 45.0
        self.reply_font = None
        self.reply_lines = []
        self.reply_starts = []
        self.auto_shots = False
        self.cps_cache = None
        self.downloading = False
        self.grab = screenshot.grab
        self.classify = self._classify
        self.ask = self._dispatch
        self.play = cues.play

    def _dispatch(self, key, model, question, image, limit, history, allow_screen=False):
        fast = bool(self.settings.get("blaze"))
        lines = int(self.settings.get("blaze_lines"))
        if self.settings.get("backend") == "claude_code":
            web = bool(self.settings.get("blaze_web" if fast else "web_search"))
            return claude_code.ask(model, question, image, limit, history, allow_screen=allow_screen,
                                   web=web, fast=fast, lines=lines)
        return api.ask(key, model, question, image, limit, history, allow_screen=allow_screen, fast=fast, lines=lines)

    def _classify(self, key, question):
        if self.settings.get("backend") == "claude_code":
            return claude_code.classify(question)
        return api.classify(key, question)

    def build(self, parent):
        f = ttk.Frame(parent)
        self.frame = f
        s = self.settings
        names = list(self.font_paths)
        default = s.get("font")
        if default not in self.font_paths:
            default = "DejaVu Sans" if "DejaVu Sans" in self.font_paths else (
                "Segoe UI" if "Segoe UI" in self.font_paths else fonts.BUILTIN)
        self.backend_var = tk.StringVar(value=s.get("backend"))
        self.key_var = tk.StringVar(value=s.get("api_key"))
        self.show_key = tk.BooleanVar(value=False)
        self.model_var = tk.StringVar(value=s.get("model"))
        self.hotkey_var = tk.StringVar(value=s.get("hotkey"))
        self.wake_var = tk.BooleanVar(value=s.get("wake_word"))
        self.shot_var = tk.StringVar(value=s.get("screenshot_mode"))
        self.sound_var = tk.BooleanVar(value=s.get("sounds"))
        self.web_var = tk.BooleanVar(value=s.get("web_search"))
        self.blaze_var = tk.BooleanVar(value=s.get("blaze"))
        self.blaze_web_var = tk.BooleanVar(value=s.get("blaze_web"))
        self.hud_var = tk.BooleanVar(value=s.get("hud"))
        self.font_var = tk.StringVar(value=default)
        self.ask_var = tk.StringVar()

        style = ttk.Style(f)
        style.configure("TNotebook", background=PANEL, borderwidth=0)
        style.configure("TNotebook.Tab", background=FIELD, foreground=TEXT, padding=(14, 4))
        style.map("TNotebook.Tab", background=[("selected", ACCENT)], foreground=[("selected", "#ffffff")])
        nb = ttk.Notebook(f)
        nb.pack(fill="x", anchor="nw")
        tabs = {}
        for name in ("Ask Claude", "Blaze", "Hosting", "Voice", "AI"):
            tabs[name] = ttk.Frame(nb, padding=(4, 8))
            nb.add(tabs[name], text=name)
        ask_tab, blaze_tab, host_tab, voice_tab, ai_tab = (tabs[n] for n in ("Ask Claude", "Blaze", "Hosting", "Voice", "AI"))

        a1 = ttk.Frame(ask_tab)
        a1.grid(row=0, column=0, sticky="nw", padx=(0, 28))
        row = ttk.Frame(a1)
        row.pack(anchor="w", pady=2)
        self.ask_entry = ttk.Entry(row, textvariable=self.ask_var, width=34)
        self.ask_entry.pack(side="left")
        self.ask_entry.bind("<Return>", lambda e: self._ask_typed())
        ttk.Button(row, text="Ask", style="Accent.TButton", command=self._ask_typed).pack(side="left", padx=6)
        row = ttk.Frame(a1)
        row.pack(anchor="w", pady=2)
        ttk.Button(row, text="Listen now", command=self.listen_now).pack(side="left")
        ttk.Button(row, text="Clear conversation", command=self._clear).pack(side="left", padx=6)
        self.status = ttk.Label(a1, text="", style="Muted.TLabel", wraplength=380, justify="left")
        self.status.pack(anchor="w", pady=(4, 2))
        self.reply_box = tk.Text(a1, width=46, height=3, bg="#22222e", fg="#e8e8f0", relief="flat", wrap="word",
                                 font=("TkDefaultFont", 10), state="disabled")
        self.reply_box.pack(anchor="w")

        a2 = ttk.Frame(ask_tab)
        a2.grid(row=0, column=1, sticky="nw", padx=(0, 28))
        for text, var, key in (
            ("Blaze mode", self.blaze_var, "blaze"),
            ("Listen for \"Hey Claude\"", self.wake_var, "wake_word"),
            ("Play sound cues", self.sound_var, "sounds"),
            ("Show the HUD card on screen", self.hud_var, "hud"),
        ):
            ttk.Checkbutton(a2, text=text, variable=var, command=lambda k=key, v=var: self._flag(k, v)).pack(
                anchor="w", pady=2)

        a3 = ttk.Frame(ask_tab)
        a3.grid(row=0, column=2, sticky="nw")
        row = ttk.Frame(a3)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Font", width=14).pack(side="left")
        fcb = ttk.Combobox(row, textvariable=self.font_var, values=names, state="readonly", width=18)
        fcb.pack(side="left")
        fcb.bind("<<ComboboxSelected>>", lambda e: self._font_changed())
        self.size = Slider(a3, "Font size (px)", 6, 24, s.get("font_size"), command=self._font_changed, integer=True)
        self.size.pack(anchor="w", pady=2)
        self.fits = ttk.Label(a3, text="", style="Muted.TLabel", wraplength=300, justify="left")
        self.fits.pack(anchor="w")

        b1 = ttk.Frame(blaze_tab)
        b1.grid(row=0, column=0, sticky="nw", padx=(0, 28))
        ttk.Checkbutton(b1, text="Blaze mode", variable=self.blaze_var,
                        command=lambda: self._flag("blaze", self.blaze_var)).pack(anchor="w", pady=2)
        ttk.Label(b1, text="Haiku, no screenshot check. A screenshot is only taken when you say screenshot, my "
                           "screen, on screen or can you see this.", style="Muted.TLabel", wraplength=420,
                  justify="left").pack(anchor="w", pady=(0, 6))
        ttk.Checkbutton(b1, text="Web research capability (only used when Claude needs it)", variable=self.blaze_web_var,
                        command=lambda: self._flag("blaze_web", self.blaze_web_var)).pack(anchor="w", pady=2)
        self.blaze_lines = Slider(b1, "Quality", 0, blaze.MAX_LINES, s.get("blaze_lines"),
                                  command=self._blaze_changed, fmt=self._lines_label, integer=True, label_width=20)
        self.blaze_lines.pack(anchor="w", pady=2)
        ttk.Label(b1, text="Max lines of reasoning before the answer. 0 is answer only. Lines of working count "
                           "towards the screen's character limit.", style="Muted.TLabel", wraplength=420,
                  justify="left").pack(anchor="w", pady=(0, 6))
        self.blaze_speed = Slider(b1, "Typing speed", 1, blaze.INSTANT, s.get("blaze_cps"),
                                  command=self._blaze_changed, fmt=blaze.speed_label, integer=True, label_width=20)
        self.blaze_speed.pack(anchor="w", pady=2)

        h1 = ttk.Frame(host_tab)
        h1.grid(row=0, column=0, sticky="nw")
        row = ttk.Frame(h1)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Use", width=10).pack(side="left")
        ttk.Radiobutton(row, text="My Claude Code login (plan usage)", value="claude_code",
                        variable=self.backend_var, command=self._backend_changed).pack(side="left")
        ttk.Radiobutton(row, text="API key (credits)", value="api", variable=self.backend_var,
                        command=self._backend_changed).pack(side="left", padx=8)
        self.backend_label = ttk.Label(h1, text="", style="Muted.TLabel", wraplength=520, justify="left")
        self.backend_label.pack(anchor="w", pady=(0, 4))
        row = ttk.Frame(h1)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="API key", width=10).pack(side="left")
        self.key_entry = ttk.Entry(row, textvariable=self.key_var, show="\u2022", width=36)
        self.key_entry.pack(side="left")
        self.key_entry.bind("<KeyRelease>", lambda e: self._save_key())
        self.key_entry.bind("<FocusOut>", lambda e: self._save_key())
        ttk.Checkbutton(row, text="Show", variable=self.show_key, command=self._toggle_key).pack(side="left", padx=6)

        v1 = ttk.Frame(voice_tab)
        v1.grid(row=0, column=0, sticky="nw", padx=(0, 28))
        row = ttk.Frame(v1)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Hotkey", width=14).pack(side="left")
        ent = ttk.Entry(row, textvariable=self.hotkey_var, width=18)
        ent.pack(side="left")
        ent.bind("<Return>", lambda e: self._apply_hotkey())
        ttk.Button(row, text="Apply", command=self._apply_hotkey).pack(side="left", padx=6)
        self.hotkey_label = ttk.Label(row, text="", style="Muted.TLabel", wraplength=230, justify="left")
        self.hotkey_label.pack(side="left")
        ttk.Checkbutton(v1, text="Listen for \"Hey Claude\"", variable=self.wake_var,
                        command=lambda: self._flag("wake_word", self.wake_var)).pack(anchor="w", pady=2)
        self.engine_var = tk.StringVar(value=s.get("voice_engine"))
        self.dict_var = tk.StringVar(value=s.get("dictation_model"))
        self.wake_model_var = tk.StringVar(value=s.get("wake_model"))
        self.gpu_var = tk.BooleanVar(value=s.get("use_gpu"))
        row = ttk.Frame(v1)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Voice engine", width=14).pack(side="left")
        ttk.Combobox(row, textvariable=self.engine_var, values=["auto", "vosk"], width=10, state="readonly").pack(side="left")
        row = ttk.Frame(v1)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Dictation", width=14).pack(side="left")
        ttk.Combobox(row, textvariable=self.dict_var, values=whispercpp.DICTATION_CHOICES, width=20,
                     state="readonly").pack(side="left")
        row = ttk.Frame(v1)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Wake word", width=14).pack(side="left")
        ttk.Combobox(row, textvariable=self.wake_model_var, values=whispercpp.WAKE_CHOICES, width=20,
                     state="readonly").pack(side="left")
        ttk.Checkbutton(v1, text="Use the GPU for Whisper", variable=self.gpu_var, command=self._voice_changed).pack(
            anchor="w", pady=2)
        for var in (self.engine_var, self.dict_var, self.wake_model_var):
            var.trace_add("write", lambda *a: self._voice_changed())
        v2 = ttk.Frame(voice_tab)
        v2.grid(row=0, column=1, sticky="nw")
        self.voice_label = ttk.Label(v2, text="", style="Muted.TLabel", wraplength=300, justify="left")
        self.voice_label.pack(anchor="w", pady=2)
        self.voice_btn = ttk.Button(v2, text="Download voice models", command=self._download)
        self.voice_btn.pack(anchor="w", pady=4)

        i1 = ttk.Frame(ai_tab)
        i1.grid(row=0, column=0, sticky="nw", padx=(0, 28))
        row = ttk.Frame(i1)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Model", width=14).pack(side="left")
        cb = ttk.Combobox(row, textvariable=self.model_var, values=MODELS, width=26)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._save_model())
        cb.bind("<FocusOut>", lambda e: self._save_model())
        cb.bind("<Return>", lambda e: self._save_model())
        ttk.Checkbutton(i1, text="Let Claude search the web", variable=self.web_var,
                        command=lambda: self._flag("web_search", self.web_var)).pack(anchor="w", pady=2)
        row = ttk.Frame(i1)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Screenshots", width=14).pack(side="left")
        shot_cb = ttk.Combobox(row, textvariable=self.shot_var, values=["auto", "always", "never"], width=8,
                               state="readonly")
        shot_cb.pack(side="left")
        shot_cb.bind("<<ComboboxSelected>>", lambda e: self._shot_changed())
        self.cps = Slider(i1, "Typing speed", 1, blaze.INSTANT, s.get("typing_cps"), command=self._cps_changed,
                          fmt=blaze.speed_label, integer=True)
        self.cps.pack(anchor="w", pady=2)
        i2 = ttk.Frame(ai_tab)
        i2.grid(row=0, column=1, sticky="nw")
        self.hud_size = Slider(i2, "HUD size", 1.0, 2.5, s.get("hud_scale"), command=self._hud_changed, fmt="{:.1f}x")
        self.hud_size.pack(anchor="w", pady=2)
        self.hud_speed = Slider(i2, "HUD animation", 1.0, 2.5, s.get("hud_speed"), command=self._hud_changed,
                                fmt="{:.1f}x")
        self.hud_speed.pack(anchor="w", pady=2)
        self._refresh_fits()
        self._refresh_voice()
        return f

    def _save(self):
        self.settings.save()

    def _backend_changed(self):
        self.settings.set("backend", self.backend_var.get())
        self._save()
        self._refresh_backend()

    def _refresh_backend(self):
        if self.backend_var.get() == "claude_code":
            path = claude_code.find()
            if path:
                self.backend_label.configure(text="Claude Code found. Questions use your plan, no API credits.")
            else:
                self.backend_label.configure(
                    text="Claude Code not found on this PC. Install it and run `claude` once to sign in.")
        else:
            self.backend_label.configure(text="Uses your API key (kept only on this PC). Costs API credits.")

    def _save_key(self):
        self.settings.set("api_key", self.key_var.get().strip())
        self._save()

    def _toggle_key(self):
        self.key_entry.configure(show="" if self.show_key.get() else "•")

    def _save_model(self):
        value = self.model_var.get().strip()
        if value:
            self.settings.set("model", value)
            self._save()

    def _flag(self, key, var):
        self.settings.set(key, bool(var.get()))
        self._save()
        if key == "wake_word" and self.active:
            self._restart_listener()
        if key == "hud" and not var.get() and self.hud is not None:
            self.hud.hide_now()
        if key == "blaze":
            if var.get():
                self._set_status("Blaze mode on: Haiku, quick answers. Screenshots only when you say screenshot or my screen.")
            else:
                self._set_status("Blaze mode off.")

    def _shot_changed(self):
        self.settings.set("screenshot_mode", self.shot_var.get())
        self._save()

    @staticmethod
    def _lines_label(value):
        return "answer only" if value == 0 else "%d" % value

    def _blaze_changed(self):
        self.settings.set("blaze_lines", int(self.blaze_lines.get()))
        self.settings.set("blaze_cps", int(self.blaze_speed.get()))
        self._save()

    def _cps_changed(self):
        self.settings.set("typing_cps", int(self.cps.get()))
        self._save()

    def _hud_changed(self):
        self.settings.set("hud_scale", float(round(self.hud_size.get(), 1)))
        self.settings.set("hud_speed", float(round(self.hud_speed.get(), 1)))
        self._save()
        if self.hud is not None:
            self.hud.configure(self.settings.get("hud_scale"), self.settings.get("hud_speed"))

    def _font_path(self):
        return self.font_paths.get(self.font_var.get())

    def _font(self):
        return fonts.load_font(self._font_path(), self.size.get())

    def _font_changed(self):
        self.settings.set("font", self.font_var.get())
        self.settings.set("font_size", int(self.size.get()))
        self._save()
        self.cps_cache = None
        self._refresh_fits()

    def limit(self):
        if self.cps_cache is None:
            self.cps_cache = capacity(self._font(), notch=NOTCH)
        return self.cps_cache

    def _refresh_fits(self):
        self.fits.configure(text="About %d characters fit at this size. Claude is told to stay under that." %
                            self.limit())

    def _refresh_voice(self):
        if self.downloading:
            return
        if voice.have_all(self.settings):
            self.voice_label.configure(text=voice.describe(self.settings))
            self.voice_btn.configure(state="disabled")
        else:
            self.voice_label.configure(text="Voice models will download (%d MB)" % voice.missing_mb(self.settings))
            self.voice_btn.configure(state="normal")

    def _download(self):
        if self.downloading:
            return
        self.downloading = True
        self.voice_btn.configure(state="disabled")
        self.voice_label.configure(text="Downloading voice models... 0%")
        self._set_status("Downloading the voice models (one-off). Typing a question still works.")
        settings = self.settings

        def work():
            try:
                voice.download_missing(settings, lambda f, label, i, n: self.events.put(("model_progress", (f, label, i, n))))
                self.events.put(("model_done", ""))
            except Exception as exc:
                self.events.put(("model_done", str(exc) or exc.__class__.__name__))

        threading.Thread(target=work, daemon=True).start()

    def _auto_download(self):
        if self.settings.get("auto_download") and not self.downloading and not voice.have_all(self.settings):
            self._download()
            return True
        return self.downloading

    def _voice_changed(self):
        self.settings.set("voice_engine", self.engine_var.get())
        self.settings.set("dictation_model", self.dict_var.get())
        self.settings.set("wake_model", self.wake_model_var.get())
        self.settings.set("use_gpu", bool(self.gpu_var.get()))
        self._save()
        self._restart_listener()
        self._refresh_voice()
        if self.active:
            self._auto_download()

    def _apply_hotkey(self):
        spec = self.hotkey_var.get().strip()
        self.settings.set("hotkey", spec)
        self._save()
        if self.active:
            self._start_hotkey()

    def _start_hotkey(self):
        spec = self.settings.get("hotkey")
        if self.hotkey.start(spec, lambda: self.events.put(("hotkey",))):
            self.hotkey_label.configure(text="Press %s anywhere to talk to Claude." % spec)
        else:
            self.hotkey_label.configure(text=self.hotkey.error)

    def _start_listener(self):
        if self.listener is not None or not voice.have_all(self.settings):
            return
        self.listener = voice.make_listener(
            self.settings,
            lambda: self.events.put(("wake",)),
            lambda text: self.events.put(("text", text)),
            lambda msg: self.events.put(("status", msg)),
            self.wake_var.get(),
        )
        self.listener.start()

    def _stop_listener(self):
        if self.listener is not None:
            self.listener.stop()
            self.listener = None

    def _restart_listener(self):
        self._stop_listener()
        if self.wake_var.get():
            self._start_listener()

    def activate(self):
        self.active = True
        if self.hud is None:
            self.hud = Hud(self.app.root, self.settings.get("hud_scale"), self.settings.get("hud_speed"))
        self.display.reset_regions()
        self.want_send = True
        self._refresh_voice()
        self._refresh_fits()
        self._refresh_backend()
        self._start_hotkey()
        if self._auto_download():
            self._set_status("Downloading the voice models (one-off). Typing a question works meanwhile.")
        elif self.wake_var.get():
            self._start_listener()
            if self.listener is not None:
                self._set_status("Listening for \"Hey Claude\". The microphone is live while this tab is open.")
            else:
                self._set_status("Voice models are missing. The hotkey and Ask box work now.")
        else:
            self._set_status("Ready. Press %s or type a question." % self.settings.get("hotkey"))
        self._idle_screen()

    def deactivate(self):
        self.active = False
        self.hotkey.stop()
        self._stop_listener()
        if self.hud is not None:
            self.hud.hide_now()
        self.phase = "idle"
        self.pending_reply = None
        self.pending_error = None

    def on_link_change(self):
        self.display.reset_regions()
        self.want_send = True

    def _set_status(self, text):
        self.status.configure(text=text)

    def _push(self, img):
        self.last_img = img
        self.want_send = True

    def _send_pending(self):
        if not self.active or self.last_img is None:
            return
        if not self.display.ready():
            return
        if self.display.take_timeout():
            self.display.reset_regions()
            self.want_send = True
        if not self.want_send and not self.display._stale:
            return
        img = self.last_img.convert("RGB")
        arr = np.asarray(img, dtype=np.uint16)
        px565 = ((arr[..., 0] & 0xF8) << 8) | ((arr[..., 1] & 0xFC) << 3) | (arr[..., 2] >> 3)
        self.want_send = False
        if self.display.regions(px565):
            self.display.flush(acked=True)

    def _idle_screen(self):
        if self.phase == "idle" and not self.reply_text:
            hint = "Say \"Hey Claude\"\nor press %s" % self.settings.get("hotkey") if self.wake_var.get() else (
                "Press %s\nto ask Claude" % self.settings.get("hotkey"))
            self._push(fonts.render_block(hint, fonts.load_font(self._font_path(), 12), DIM, BG))

    def _board_spin(self, caption):
        self.board_caption = caption
        self.spin_t0 = time.perf_counter()
        self.spin_bucket = -1
        self._board_frame(self.spin_t0)

    def _board_frame(self, now):
        angle = ((now - self.spin_t0) * 140.0) % 360.0
        self.frozen_angle = angle
        img = fonts.render_block(self.board_caption, fonts.load_font(self._font_path(), 12), DIM, BG)
        icon = starburst(angle, ICON)
        img.paste(icon, (fonts.WIDTH - ICON - 3, 3), icon)
        self._push(img)

    def _screen_status(self, text, colour=DIM):
        self._push(fonts.render_block(text, fonts.load_font(self._font_path(), 12), colour, BG))

    def _cue(self, kind):
        if self.settings.get("sounds"):
            self.play(kind)

    def _hud(self, kind, seconds=None, detail=None):
        if self.hud is not None and self.settings.get("hud"):
            self.hud.show(kind, seconds, detail)

    def _error_hud(self, message):
        code, short = error_info(message)
        self._cue("error")
        self._hud("error", 4.5, ("Error %s" % code, short))
        return code

    def listen_now(self):
        self.begin_listen(True)

    def begin_listen(self, request):
        if self.phase != "idle":
            return
        if not voice.have_all(self.settings):
            if self._auto_download():
                self._set_status("Downloading the voice models first (one-off), then press %s again." %
                                 self.settings.get("hotkey"))
                self._hud("thinking", 4.0, ("Getting voice models", "Press again soon"))
                return
            message = "Download the voice models first (button in Setup). You can still type a question."
            code = self._error_hud(message)
            self._set_status("%s: %s" % (code, message))
            return
        if self.listener is None:
            self._start_listener()
        if self.listener is None:
            return
        self.phase = "listening"
        self.listen_since = time.perf_counter()
        if request:
            self.listener.dictate()
        self._cue("listening")
        self._hud("listening")
        self._screen_status("Listening...")
        self._set_status("Listening... speak now.")

    def _ask_typed(self):
        text = self.ask_var.get().strip()
        if not text or self.phase != "idle":
            return
        self.ask_var.set("")
        self.submit(text)

    def _clear(self):
        self.history = []
        self.reply_text = ""
        self._set_status("Conversation cleared.")
        self._idle_screen()

    def submit(self, question):
        key = self.settings.api_key()
        if self.settings.get("backend") == "claude_code":
            if not claude_code.find() and self.ask == self._dispatch:
                self._fail("Claude Code was not found. Install it and sign in, or switch to an API key in Setup.")
                return
        elif not key:
            self._fail("No API key yet. Paste one into Setup, or switch to Claude Code.")
            return
        self.question = question
        self.pending_reply = None
        self.pending_error = None
        mode = self.settings.get("screenshot_mode")
        fast = bool(self.settings.get("blaze"))
        model = api.HAIKU if fast else self.settings.get("model")
        if mode == "never":
            take = False
        elif fast:
            take = smartshot.blaze_wants_screen(question)
        elif mode == "always":
            take = True
        else:
            take = smartshot.wants_screen(question)
        self.run_ctx = (key, model, question, self.limit(), list(self.history))
        self.auto_shots = mode == "auto" and not fast
        image = None
        if take:
            image = self._take_shot()
            if image is None:
                return
        else:
            self.phase = "thinking"
            self._cue("thinking")
            self._hud("thinking")
            self._board_spin("Thinking...")
        self._set_status("Asking Claude: %s" % question)
        self._run(image, self.auto_shots and image is None)

    def _take_shot(self):
        if self.hud is not None:
            self.hud.hide_now()
            self.app.root.update_idletasks()
            time.sleep(0.12)
        try:
            image = self.grab()
        except Exception as exc:
            self._fail("Could not take a screenshot: %s" % exc)
            return None
        dur = 5.9 / max(0.5, self.settings.get("hud_speed"))
        self.shot_until = time.perf_counter() + dur
        self.phase = "shot"
        self._cue("screenshot")
        self._hud("screenshot", dur)
        self._board_spin("Looking at your screen...")
        return image

    def _run(self, image, classify_first):
        key, model, question, limit, history = self.run_ctx

        def work():
            try:
                if classify_first:
                    try:
                        needs = self.classify(key, question)
                    except Exception:
                        needs = False
                    if needs:
                        self.events.put(("need_screen",))
                        return
                allow = classify_first and image is None
                if allow:
                    reply = self.ask(key, model, question, image, limit, history, allow_screen=True)
                    if smartshot.wants_more(reply):
                        self.events.put(("need_screen",))
                        return
                else:
                    reply = self.ask(key, model, question, image, limit, history)
                self.events.put(("reply", reply))
            except api.AssistantError as exc:
                self.events.put(("error", str(exc)))
            except Exception as exc:
                self.events.put(("error", "Something broke: %s" % exc))

        threading.Thread(target=work, daemon=True).start()

    def _cancel(self):
        self.phase = "idle"
        self.pending_reply = None
        self.pending_error = None
        if self.hud is not None:
            self.hud.hide_now()
        self._set_status("Cancelled. Nothing was sent.")
        self.reply_text = ""
        self._idle_screen()
        if self.listener is not None:
            self.listener.pause(False)

    def _fail(self, message):
        self.phase = "idle"
        self.pending_reply = None
        self.pending_error = None
        code = self._error_hud(message)
        self._set_status("%s: %s" % (code, message))
        spinning = self.board_caption is not None
        self.board_caption = None
        frame = fonts.render_block("Error %s\n%s" % (code, message[:60]), fonts.load_font(self._font_path(), 12), BAD, BG)
        if spinning:
            icon = starburst(NEUTRAL, ICON)
            frame.paste(icon, (fonts.WIDTH - ICON - 3, 3), icon)
        self._push(frame)
        self.reply_text = ""
        if self.listener is not None:
            self.listener.pause(False)

    def _start_typing(self, text):
        base = self._font()
        fitted = fit_reply(text, base, notch=NOTCH)
        font = base
        self.board_caption = None
        self.reply_text = fitted
        self.reply_font = font
        self.reply_lines = fonts.layout(fitted, font, notch=NOTCH)[0]
        self.reply_starts = self._line_starts(fitted, self.reply_lines)
        self.history.append(("user", self.question))
        self.history.append(("assistant", text))
        del self.history[:-12]
        cps = int(self.settings.get("blaze_cps" if self.settings.get("blaze") else "typing_cps"))
        self.schedule = TypeSchedule(fitted, cps)
        self.type_start = time.perf_counter()
        self.stop_from = self.frozen_angle
        self.stop_to = self._neutral_after(self.frozen_angle)
        self.frozen_angle = self.stop_to
        self.shown_key = None
        self.phase = "typing"
        self._cue("responding")
        self._hud("responding")
        self.reply_box.configure(state="normal")
        self.reply_box.delete("1.0", "end")
        self.reply_box.insert("1.0", text)
        self.reply_box.configure(state="disabled")
        self._set_status("Typing the reply onto the screen.")

    @staticmethod
    def _line_starts(text, lines):
        starts = []
        pos = 0
        for line in lines:
            at = text.find(line, pos) if line else pos
            if at < 0:
                at = pos
            starts.append(at)
            pos = at + len(line)
        return starts

    @staticmethod
    def _neutral_after(angle):
        target = (int((angle - 45.0) // 90.0) + 1) * 90.0 + 45.0
        if target - angle < 25.0:
            target += 90.0
        return target

    def _icon_angle(self, now):
        t = min(1.0, max(0.0, (now - self.type_start) / SETTLE))
        eased = 1 - (1 - t) ** 3
        return self.stop_from + (self.stop_to - self.stop_from) * eased

    def _final_frame(self):
        try:
            self._render_reply(self.schedule.size, False, NEUTRAL)
        except Exception:
            img = Image.new("RGB", (fonts.WIDTH, fonts.HEIGHT), BG)
            icon = starburst(NEUTRAL, ICON)
            img.paste(icon, (fonts.WIDTH - ICON - 3, 3), icon)
            self._push(img)

    def _render_reply(self, count, cursor, angle):
        shown = []
        for line, start in zip(self.reply_lines, self.reply_starts):
            if count <= start and shown:
                break
            shown.append(self.reply_text[start:min(start + len(line), count)] if count > start else "")
        if cursor and shown:
            shown[-1] += "_"
        img = fonts.draw_lines(shown, self.reply_font, FG, BG, notch=NOTCH)
        icon = starburst(angle % 360.0, ICON)
        img.paste(icon, (fonts.WIDTH - ICON - 3, 3), icon)
        self._push(img)

    def tick(self, dt):
        self._tick_phase()
        self._send_pending()

    def _tick_phase(self):
        self._pump()
        now = time.perf_counter()
        if self.phase in ("shot", "thinking") and self.board_caption is not None:
            bucket = int((now - self.spin_t0) * 12)
            if bucket != self.spin_bucket:
                self.spin_bucket = bucket
                self._board_frame(now)
        if self.phase == "shot" and now >= self.shot_until:
            if self.pending_reply is not None:
                self._start_typing(self.pending_reply)
                self.pending_reply = None
            elif self.pending_error is not None:
                self._fail(self.pending_error)
            else:
                self.phase = "thinking"
                self._cue("thinking")
                self._hud("thinking")
                self._board_spin("Thinking...")
        elif self.phase == "thinking":
            if self.pending_reply is not None:
                self._start_typing(self.pending_reply)
                self.pending_reply = None
            elif self.pending_error is not None:
                self._fail(self.pending_error)
        elif self.phase == "typing":
            n = self.schedule.count(now - self.type_start)
            typed = n >= self.schedule.size
            done = typed and now - self.type_start >= SETTLE
            cursor = (not typed) and int((now - self.type_start) * 2.5) % 2 == 0
            angle = self._icon_angle(now)
            key = (n, cursor, done, int(angle))
            if key != self.shown_key:
                self.shown_key = key
                self._render_reply(n, cursor, angle)
            if done:
                self.phase = "idle"
                self._final_frame()
                self._cue("done")
                self._hud("done", 3.2)
                self._set_status("Done. Press %s to ask again." % self.settings.get("hotkey"))
        elif self.phase == "listening" and now - self.listen_since > LISTEN_GIVE_UP:
            self._fail("I didn't hear anything.")

    def _pump(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return
            kind = event[0]
            if kind == "hotkey":
                self.begin_listen(True)
            elif kind == "wake":
                if self.phase == "idle":
                    self.phase = "listening"
                    self.listen_since = time.perf_counter()
                    self._cue("listening")
                    self._hud("listening")
                    self._screen_status("Listening...")
                    self._set_status("Listening... speak now.")
            elif kind == "text":
                if self.phase == "listening":
                    if event[1] and smartshot.is_cancel(event[1]):
                        self._cancel()
                    elif event[1]:
                        self.submit(event[1])
                    else:
                        reason = getattr(self.listener, "reason", "")
                        if reason == "silence":
                            self._fail("I didn't hear anything. Is the mic too quiet?")
                        elif reason.startswith("engine"):
                            self._fail("I didn't catch that. The voice engine failed: %s" % reason[8:])
                        elif reason == "empty":
                            self._fail("I didn't catch that. I heard sound but no words.")
                        else:
                            self._fail("I didn't catch that.")
            elif kind == "need_screen":
                if self.phase in ("shot", "thinking"):
                    image = self._take_shot()
                    if image is not None:
                        self._set_status("Your question looks like it needs your screen. Looking...")
                        self._run(image, False)
            elif kind == "reply":
                if self.phase in ("shot", "thinking"):
                    self.pending_reply = event[1]
            elif kind == "error":
                if self.phase in ("shot", "thinking"):
                    self.pending_error = event[1]
            elif kind == "status":
                self._set_status(event[1])
            elif kind == "model_progress":
                frac, label, index, total = event[1]
                self.voice_label.configure(text="Downloading %s (%d of %d)... %d%%" % (label, index, total, int(frac * 100)))
            elif kind == "model_done":
                self.downloading = False
                if event[1]:
                    self.voice_label.configure(text="Download failed: %s" % event[1])
                    self.voice_btn.configure(state="normal")
                else:
                    self._refresh_voice()
                    if self.active:
                        self._start_listener()
                        if self.wake_var.get():
                            self._set_status("Listening for \"Hey Claude\".")
                        else:
                            self._set_status("Voice models ready. Press %s to talk." % self.settings.get("hotkey"))
