import time
import tkinter as tk
from tkinter import ttk

import numpy as np

from ..audiovis import colors
from ..audiovis.analysis import TRIGGERS, Analyser
from ..audiovis.capture import AUTO_DEVICE, DemoSource, LoopbackCapture
from ..audiovis.raster import Raster
from ..audiovis.visuals import VISUALS, Look
from ..display import H, W
from ..widgets import ColorField, Slider
from .base import Mode

VISUAL_LABELS = {
    "radial_wave": "Radial spectrum + bass ring + waveform",
    "wave": "Waveform only",
    "radial": "Radial spectrum + bass ring",
    "bars": "Mirrored peak-hold bars",
}
MODE_LABELS = {
    colors.MODE_LOUDNESS: "Loudness gradient: pink to red",
    colors.MODE_FIXED: "Custom colour",
    colors.MODE_RAINBOW: "Rainbow (red centre to pink)",
}
TRIGGER_LABELS = {"kick": "Kick", "bass": "Bass"}
DEMO_DEVICE = "Demo signal"
FAILED = ("PyAudioWPatch", "Audio error", "No audio")
DEFAULT_HEX = "#ff0000"


def reverse_lookup(table, label, default):
    for key, value in table.items():
        if value == label:
            return key
    return default


class VisualiserMode(Mode):
    name = "Visualiser"
    blurb = "The audio visualiser, drawn for the screen"

    def __init__(self, app):
        super().__init__(app)
        self.source = None
        self.analyser = Analyser()
        self.raster = Raster(W, H, False)
        self.look = Look(colors.MODE_RAINBOW, colors.parse_hex(DEFAULT_HEX), 1.6, 1.6, 0.5)
        self.look.hold = 0.0
        self.visual = VISUALS["radial_wave"]()
        self.accum = 0.0
        self.last = time.perf_counter()
        self.device_values = []
        self.frames = 0
        self.demo = False
        self.shown = None
        self.prev = None

    def build(self, parent):
        f = ttk.Frame(parent)
        self.frame = f
        self.visual_var = tk.StringVar(value=VISUAL_LABELS["radial_wave"])
        self.mode_var = tk.StringVar(value=MODE_LABELS[colors.MODE_RAINBOW])
        self.trigger_var = tk.StringVar(value=TRIGGER_LABELS["kick"])
        self.device_var = tk.StringVar(value=AUTO_DEVICE)
        self.fps_var = tk.StringVar(value="30")
        self.norm_var = tk.BooleanVar(value=True)
        self.infinite_var = tk.BooleanVar(value=False)

        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky="n", padx=(0, 24))
        mid = ttk.Frame(f)
        mid.grid(row=0, column=1, sticky="n", padx=(0, 24))
        right = ttk.Frame(f)
        right.grid(row=0, column=2, sticky="n")

        row = ttk.Frame(left)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Visual", width=10).pack(side="left")
        box = ttk.Combobox(row, textvariable=self.visual_var, values=list(VISUAL_LABELS.values()),
                           state="readonly", width=34)
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda e: self._on_visual())
        row = ttk.Frame(left)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Colour", width=10).pack(side="left")
        box = ttk.Combobox(row, textvariable=self.mode_var, values=list(MODE_LABELS.values()),
                           state="readonly", width=28)
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda e: self._on_mode())
        self.fixed = ColorField(left, "Custom colour", DEFAULT_HEX, command=self._on_hex)
        self.fixed.pack(anchor="w", pady=2)
        row = ttk.Frame(left)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Audio", width=10).pack(side="left")
        self.device_box = ttk.Combobox(row, textvariable=self.device_var, values=[AUTO_DEVICE, DEMO_DEVICE],
                                       state="readonly", width=34)
        self.device_box.pack(side="left")
        self.device_box.bind("<<ComboboxSelected>>", lambda e: self._on_device())
        row = ttk.Frame(left)
        row.pack(anchor="w", pady=2)
        ttk.Button(row, text="Restart capture", command=self._restart).pack(side="left")
        ttk.Label(row, text="Frame rate", style="Muted.TLabel").pack(side="left", padx=(14, 6))
        ttk.Combobox(row, textvariable=self.fps_var, values=("15", "20", "30", "40"), state="readonly",
                     width=4).pack(side="left")
        self.source_note = ttk.Label(left, text="", style="Muted.TLabel", wraplength=330, justify="left")
        self.source_note.pack(anchor="w", pady=6)

        self.sens = Slider(mid, "Sensitivity", 0.05, 3.0, 1.6, command=self._on_sens)
        self.sens.pack(anchor="w", pady=2)
        self.smooth = Slider(mid, "Line smoothness", 0.0, 1.0, 0.5, command=self._on_smooth)
        self.smooth.pack(anchor="w", pady=2)
        self.bar_smooth = Slider(mid, "Bar smoothness", 0.0, 1.0, 0.35)
        self.bar_smooth.pack(anchor="w", pady=2)
        self.ring = Slider(mid, "Ring size", 0.5, 8.0, 1.6, command=self._on_ring)
        self.ring.pack(anchor="w", pady=2)
        self.detect = Slider(mid, "Detection", 0.25, 8.0, 1.6, command=self._on_detect)
        self.detect.pack(anchor="w", pady=2)
        ttk.Checkbutton(mid, text="Normalise (react to changes)", variable=self.norm_var,
                        command=self._on_norm).pack(anchor="w", pady=2)
        row = ttk.Frame(mid)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Bass ring reacts to").pack(side="left", padx=(0, 6))
        box = ttk.Combobox(row, textvariable=self.trigger_var, values=list(TRIGGER_LABELS.values()),
                           state="readonly", width=8)
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda e: self._on_trigger())

        ttk.Label(right, text="Peak markers (bars)", style="Muted.TLabel").pack(anchor="w")
        self.hold = Slider(right, "Hold time (s)", 0.0, 15.0, 0.0, command=self._on_hold, fmt="{:.1f}")
        self.hold.pack(anchor="w", pady=2)
        ttk.Checkbutton(right, text="Hold until pushed up", variable=self.infinite_var,
                        command=self._on_hold).pack(anchor="w", pady=2)
        return f

    def _on_visual(self):
        name = reverse_lookup(VISUAL_LABELS, self.visual_var.get(), "radial_wave")
        self.visual = VISUALS[name]()

    def _on_mode(self):
        self.look.mode = reverse_lookup(MODE_LABELS, self.mode_var.get(), colors.MODE_LOUDNESS)

    def _on_hex(self):
        self.look.fixed = self.fixed.get()
        self.look.mode = colors.MODE_FIXED
        self.mode_var.set(MODE_LABELS[colors.MODE_FIXED])

    def _on_sens(self):
        self.look.sensitivity = self.sens.get()

    def _on_smooth(self):
        self.look.smooth = self.smooth.get()

    def _on_ring(self):
        self.look.ring = self.ring.get()

    def _on_detect(self):
        self.analyser.ring_sens = self.detect.get()

    def _on_norm(self):
        self.analyser.normalise = bool(self.norm_var.get())

    def _on_trigger(self):
        self.analyser.set_trigger(reverse_lookup(TRIGGER_LABELS, self.trigger_var.get(), "kick"))

    def _on_hold(self):
        self.look.hold = 1e9 if self.infinite_var.get() else self.hold.get()

    def _on_device(self):
        self._restart()

    def _restart(self):
        self._stop_source()
        self._start_source()

    def _start_source(self):
        want = self.device_var.get()
        self.demo = want == DEMO_DEVICE
        if self.demo:
            self.source = DemoSource()
            self.source_note.configure(text="Source: demo signal")
            return
        src = LoopbackCapture()
        if want != AUTO_DEVICE:
            src._device = want
        src.start()
        if src.status.startswith(FAILED):
            note = src.status
            src.close()
            src = DemoSource()
            self.source_note.configure(text="Using the demo signal. " + note)
        else:
            self.source_note.configure(text=src.status)
        self.source = src

    def _stop_source(self):
        if self.source is not None:
            self.source.close()
        self.source = None

    def activate(self):
        self._start_source()
        self.accum = 0.0
        self.display.reset_regions()
        self.last = time.perf_counter()
        self.display.clear((0, 0, 0))
        self.display.flush()

    def deactivate(self):
        self._stop_source()

    def _send(self, px):
        arr = px.astype(np.uint16)
        px565 = ((arr[..., 0] & 0xF8) << 8) | ((arr[..., 1] & 0xFC) << 3) | (arr[..., 2] >> 3)
        if self.display.regions(px565):
            self.display.flush(acked=True)

    def _smooth_bars(self, step):
        s = self.bar_smooth.get()
        vals = np.asarray(self.analyser.vals, dtype=np.float64)
        if self.shown is None or len(self.shown) != len(vals) or s <= 0.001:
            self.shown = vals.copy()
            return
        attack = 1.0 - np.exp(-step / max(1e-4, s * 0.06))
        release = 1.0 - np.exp(-step / (0.02 + s * 0.4))
        rising = vals > self.shown
        self.shown = self.shown + (vals - self.shown) * np.where(rising, attack, release)
        self.analyser.vals = self.shown.copy()

    def _refresh_status(self):
        src = self.source
        if src is None or isinstance(src, DemoSource):
            return
        text = src.status
        if src.is_silent():
            text += " (no audio playing)"
        self.source_note.configure(text=text)
        values = [AUTO_DEVICE] + [d for d in src.devices() if d != AUTO_DEVICE] + [DEMO_DEVICE]
        if values != self.device_values:
            self.device_values = values
            self.device_box.configure(values=values)

    def tick(self, dt):
        if self.source is None:
            return
        self.accum += dt
        if not self.display.ready():
            return
        if self.accum < 1.0 / float(self.fps_var.get()):
            return
        step = min(0.1, max(0.001, self.accum))
        self.accum = 0.0
        now = time.perf_counter()
        self.analyser.set_rate(self.source.rate)
        self.analyser.update(self.source.latest(), step, now)
        self._smooth_bars(step)
        prims = self.visual.frame(W, H, step, self.analyser, self.look, True)
        px = np.ascontiguousarray(self.raster.render(prims))
        if self.display.take_timeout():
            self.display.reset_regions()
        self._send(px)
        self.frames += 1
        if self.frames % 20 == 1:
            self._refresh_status()
