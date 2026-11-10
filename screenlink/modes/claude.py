import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from .. import fonts
from ..assistant import api, cues, hotkey, screenshot, speech
from ..assistant.hud import Hud
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
        self.cps_cache = None
        self.downloading = False
        self.grab = screenshot.grab
        self.ask = api.ask
        self.play = cues.play

    def build(self, parent):
        f = ttk.Frame(parent)
        self.frame = f
        s = self.settings
        names = list(self.font_paths)
        default = s.get("font")
        if default not in self.font_paths:
            default = "DejaVu Sans" if "DejaVu Sans" in self.font_paths else (
                "Segoe UI" if "Segoe UI" in self.font_paths else fonts.BUILTIN)
        self.key_var = tk.StringVar(value=s.get("api_key"))
        self.show_key = tk.BooleanVar(value=False)
        self.model_var = tk.StringVar(value=s.get("model"))
        self.hotkey_var = tk.StringVar(value=s.get("hotkey"))
        self.wake_var = tk.BooleanVar(value=s.get("wake_word"))
        self.shot_var = tk.BooleanVar(value=s.get("screenshot"))
        self.sound_var = tk.BooleanVar(value=s.get("sounds"))
        self.hud_var = tk.BooleanVar(value=s.get("hud"))
        self.font_var = tk.StringVar(value=default)
        self.ask_var = tk.StringVar()

        style = ttk.Style(f)
        style.configure("TNotebook", background=PANEL, borderwidth=0)
        style.configure("TNotebook.Tab", background=FIELD, foreground=TEXT, padding=(14, 4))
        style.map("TNotebook.Tab", background=[("selected", ACCENT)], foreground=[("selected", "#ffffff")])
        nb = ttk.Notebook(f)
        nb.pack(fill="x", anchor="nw")
        ask_tab = ttk.Frame(nb, padding=(4, 8))
        set_tab = ttk.Frame(nb, padding=(4, 8))
        nb.add(ask_tab, text="Ask Claude")
        nb.add(set_tab, text="Setup")

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
            ("Listen for \"Hey Claude\"", self.wake_var, "wake_word"),
            ("Send a screenshot with each question", self.shot_var, "screenshot"),
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
        self.cps = Slider(a3, "Typing speed", 6, 90, s.get("typing_cps"), command=self._cps_changed,
                          fmt="{:.0f} /s", integer=True)
        self.cps.pack(anchor="w", pady=2)
        self.fits = ttk.Label(a3, text="", style="Muted.TLabel", wraplength=300, justify="left")
        self.fits.pack(anchor="w")

        s1 = ttk.Frame(set_tab)
        s1.grid(row=0, column=0, sticky="nw", padx=(0, 28))
        row = ttk.Frame(s1)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="API key", width=10).pack(side="left")
        self.key_entry = ttk.Entry(row, textvariable=self.key_var, show="\u2022", width=30)
        self.key_entry.pack(side="left")
        self.key_entry.bind("<KeyRelease>", lambda e: self._save_key())
        self.key_entry.bind("<FocusOut>", lambda e: self._save_key())
        ttk.Checkbutton(row, text="Show", variable=self.show_key, command=self._toggle_key).pack(side="left", padx=6)
        row = ttk.Frame(s1)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Model", width=10).pack(side="left")
        cb = ttk.Combobox(row, textvariable=self.model_var, values=MODELS, width=26)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._save_model())
        cb.bind("<FocusOut>", lambda e: self._save_model())
        cb.bind("<Return>", lambda e: self._save_model())
        row = ttk.Frame(s1)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Hotkey", width=10).pack(side="left")
        ent = ttk.Entry(row, textvariable=self.hotkey_var, width=18)
        ent.pack(side="left")
        ent.bind("<Return>", lambda e: self._apply_hotkey())
        ttk.Button(row, text="Apply", command=self._apply_hotkey).pack(side="left", padx=6)
        self.hotkey_label = ttk.Label(s1, text="", style="Muted.TLabel", wraplength=380, justify="left")
        self.hotkey_label.pack(anchor="w")
        ttk.Label(s1, text="The key is kept only on this PC (console.anthropic.com to get one).",
                  style="Muted.TLabel", wraplength=380, justify="left").pack(anchor="w", pady=(4, 0))

        s2 = ttk.Frame(set_tab)
        s2.grid(row=0, column=1, sticky="nw")
        row = ttk.Frame(s2)
        row.pack(anchor="w", pady=2)
        self.voice_label = ttk.Label(row, text="", style="Muted.TLabel", wraplength=230, justify="left")
        self.voice_label.pack(side="left")
        self.voice_btn = ttk.Button(row, text="Download voice model", command=self._download)
        self.voice_btn.pack(side="left", padx=8)
        self.hud_size = Slider(s2, "HUD size", 1.0, 2.5, s.get("hud_scale"), command=self._hud_changed, fmt="{:.1f}x")
        self.hud_size.pack(anchor="w", pady=2)
        self.hud_speed = Slider(s2, "HUD animation", 1.0, 2.5, s.get("hud_speed"), command=self._hud_changed,
                                fmt="{:.1f}x")
        self.hud_speed.pack(anchor="w", pady=2)
        self._refresh_fits()
        self._refresh_voice()
        return f

    def _save(self):
        self.settings.save()

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
            self.cps_cache = capacity(self._font())
        return self.cps_cache

    def _refresh_fits(self):
        self.fits.configure(text="About %d characters fit at this size. Claude is told to stay under that." %
                            self.limit())

    def _refresh_voice(self):
        if speech.have_model():
            self.voice_label.configure(text="Voice model installed")
            self.voice_btn.configure(state="disabled")
        else:
            self.voice_label.configure(text="Voice needs a one-off 40 MB download")
            self.voice_btn.configure(state="normal")

    def _download(self):
        if self.downloading:
            return
        self.downloading = True
        self.voice_btn.configure(state="disabled")
        self.voice_label.configure(text="Downloading... 0%")

        def work():
            try:
                speech.download_model(lambda f: self.events.put(("model_progress", f)))
                self.events.put(("model_done", ""))
            except Exception as exc:
                self.events.put(("model_done", str(exc) or exc.__class__.__name__))

        threading.Thread(target=work, daemon=True).start()

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
        if self.listener is not None or not speech.have_model():
            return
        self.listener = speech.Listener(
            lambda: self.events.put(("wake",)),
            lambda text: self.events.put(("text", text)),
            lambda msg: self.events.put(("status", msg)),
            wake_enabled=self.wake_var.get(),
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
        self._refresh_voice()
        self._refresh_fits()
        self._start_hotkey()
        if self.wake_var.get():
            self._start_listener()
            if self.listener is not None:
                self._set_status("Listening for \"Hey Claude\". The microphone is live while this tab is open.")
            else:
                self._set_status("Download the voice model to use \"Hey Claude\". The hotkey and Ask box work now.")
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
        if self.last_img is not None:
            self._push(self.last_img)

    def _set_status(self, text):
        self.status.configure(text=text)

    def _push(self, img):
        self.last_img = img
        self.display.full_image(img)
        self.display.flush(realtime=True)

    def _idle_screen(self):
        if self.phase == "idle" and not self.reply_text:
            hint = "Say \"Hey Claude\"\nor press %s" % self.settings.get("hotkey") if self.wake_var.get() else (
                "Press %s\nto ask Claude" % self.settings.get("hotkey"))
            self._push(fonts.render_block(hint, fonts.load_font(self._font_path(), 12), DIM, BG))

    def _screen_status(self, text, colour=DIM):
        self._push(fonts.render_block(text, fonts.load_font(self._font_path(), 12), colour, BG))

    def _cue(self, kind):
        if self.settings.get("sounds"):
            self.play(kind)

    def _hud(self, kind, seconds=None):
        if self.hud is not None and self.settings.get("hud"):
            self.hud.show(kind, seconds)

    def listen_now(self):
        self.begin_listen(True)

    def begin_listen(self, request):
        if self.phase != "idle":
            return
        if not speech.have_model():
            self._set_status("Download the voice model first (button on the left). You can still type a question.")
            self._cue("error")
            self._hud("error", 3.9)
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
        if not key:
            self._fail("No API key yet. Paste one into the API key box.")
            return
        self.question = question
        self.pending_reply = None
        self.pending_error = None
        image = None
        if self.settings.get("screenshot"):
            if self.hud is not None:
                self.hud.hide_now()
                self.app.root.update_idletasks()
                time.sleep(0.12)
            try:
                image = self.grab()
            except Exception as exc:
                self._fail("Could not take a screenshot: %s" % exc)
                return
            dur = 5.9 / max(0.5, self.settings.get("hud_speed"))
            self.shot_until = time.perf_counter() + dur
            self.phase = "shot"
            self._cue("screenshot")
            self._hud("screenshot", dur)
            self._screen_status("Looking at your screen...")
        else:
            self.phase = "thinking"
            self._cue("thinking")
            self._hud("thinking")
            self._screen_status("Thinking...")
        self._set_status("Asking Claude: %s" % question)
        model = self.settings.get("model")
        limit = self.limit()
        history = list(self.history)

        def work():
            try:
                self.events.put(("reply", self.ask(key, model, question, image, limit, history)))
            except api.AssistantError as exc:
                self.events.put(("error", str(exc)))
            except Exception as exc:
                self.events.put(("error", "Something broke: %s" % exc))

        threading.Thread(target=work, daemon=True).start()

    def _fail(self, message):
        self.phase = "idle"
        self.pending_reply = None
        self.pending_error = None
        self._set_status(message)
        self._cue("error")
        self._hud("error", 3.9)
        self._screen_status("Error\n" + message[:60], BAD)
        self.reply_text = ""
        if self.listener is not None:
            self.listener.pause(False)

    def _start_typing(self, text):
        font = self._font()
        fitted = fit_reply(text, font)
        self.reply_text = fitted
        self.history.append(("user", self.question))
        self.history.append(("assistant", text))
        del self.history[:-12]
        self.schedule = TypeSchedule(fitted, self.settings.get("typing_cps"))
        self.type_start = time.perf_counter()
        self.shown_key = None
        self.phase = "typing"
        self._cue("responding")
        self._hud("responding")
        self.reply_box.configure(state="normal")
        self.reply_box.delete("1.0", "end")
        self.reply_box.insert("1.0", text)
        self.reply_box.configure(state="disabled")
        self._set_status("Typing the reply onto the screen.")

    def _render_reply(self, count, cursor):
        text = self.reply_text[:count] + ("_" if cursor else "")
        img = fonts.render_block(text, self._font(), FG, BG, "left", "top")
        self._push(img)

    def tick(self, dt):
        self._pump()
        now = time.perf_counter()
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
                self._screen_status("Thinking...")
        elif self.phase == "thinking":
            if self.pending_reply is not None:
                self._start_typing(self.pending_reply)
                self.pending_reply = None
            elif self.pending_error is not None:
                self._fail(self.pending_error)
        elif self.phase == "typing":
            n = self.schedule.count(now - self.type_start)
            done = n >= self.schedule.size
            cursor = (not done) and int((now - self.type_start) * 2.5) % 2 == 0
            key = (n, cursor, done)
            if key != self.shown_key:
                self.shown_key = key
                self._render_reply(n, cursor)
            if done:
                self.phase = "idle"
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
                    if event[1]:
                        self.submit(event[1])
                    else:
                        self._fail("I didn't catch that.")
            elif kind == "reply":
                if self.phase in ("shot", "thinking"):
                    self.pending_reply = event[1]
            elif kind == "error":
                if self.phase in ("shot", "thinking"):
                    self.pending_error = event[1]
            elif kind == "status":
                self._set_status(event[1])
            elif kind == "model_progress":
                self.voice_label.configure(text="Downloading... %d%%" % int(event[1] * 100))
            elif kind == "model_done":
                self.downloading = False
                if event[1]:
                    self.voice_label.configure(text="Download failed: %s" % event[1])
                    self.voice_btn.configure(state="normal")
                else:
                    self._refresh_voice()
                    if self.active and self.wake_var.get():
                        self._start_listener()
                        self._set_status("Listening for \"Hey Claude\".")
