import tkinter as tk
from tkinter import ttk

import numpy as np

from .. import colors
from ..analysis import Analyser
from ..capture import make_source
from ..display import H, W
from ..peaks import PeakHold
from ..widgets import ColorField, Slider
from .base import Mode

RADIAL_WAVE = "Radial + bass ring + waveform"
RADIAL = "Radial + bass ring"
STYLES = (RADIAL_WAVE, RADIAL, "Peak-hold bars", "Mirrored bars", "Oscilloscope")
CX, CY = W // 2, H // 2
R_MAX = H // 2 - 1
R_IN = round(H * 0.19)
BACK = 0.55                 # how far bars fade back to red towards their tips
COLOUR_MODES = {
    "Rainbow by frequency": colors.MODE_RAINBOW,
    "Custom colour": colors.MODE_FIXED,
}
SOURCES = {"System audio (loopback)": "loopback", "Demo signal": "demo"}


class VisualiserMode(Mode):
    name = "Visualiser"
    blurb = "Audio visualiser fed by your PC's sound"
    STYLES = STYLES
    BARS_SPEC = (8, 96, 48)
    SENS_SPEC = (0.05, 8.0, 1.0)

    def __init__(self, app):
        super().__init__(app)
        self.source = None
        self.analyser = None
        self.peaks = PeakHold(32)
        self.accum = 0.0
        self.palette = []
        self.palette_n = 0
        self.last_levels = np.zeros(32)
        self.bass_env = 0.0
        self.wave_prev = None
        self.wave_ref = 0.1

    def build(self, parent):
        f = ttk.Frame(parent)
        self.frame = f
        self.style_var = tk.StringVar(value=self.STYLES[0])
        self.colour_var = tk.StringVar(value="Rainbow by frequency")
        self.source_var = tk.StringVar(value="System audio (loopback)")
        self.fps_var = tk.StringVar(value="40")
        self.infinite_var = tk.BooleanVar(value=False)

        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky="n", padx=(0, 24))
        mid = ttk.Frame(f)
        mid.grid(row=0, column=1, sticky="n", padx=(0, 24))
        right = ttk.Frame(f)
        right.grid(row=0, column=2, sticky="n")

        row = ttk.Frame(left)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Style", width=14).pack(side="left")
        cb = ttk.Combobox(row, textvariable=self.style_var, values=self.STYLES, state="readonly", width=28)
        cb.pack(side="left")
        row = ttk.Frame(left)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Colour", width=14).pack(side="left")
        ttk.Combobox(row, textvariable=self.colour_var, values=list(COLOUR_MODES), state="readonly",
                     width=26).pack(side="left")
        self.fixed = ColorField(left, "Custom colour", "#ff2d55")
        self.fixed.pack(anchor="w", pady=2)
        lo, hi, start = self.BARS_SPEC
        self.bars = Slider(left, "Bars", lo, hi, start, command=self._bars_changed, integer=True)
        self.bars.pack(anchor="w", pady=2)
        self.peaks.resize(self.bars.get())
        row = ttk.Frame(left)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Audio source", width=14).pack(side="left")
        src = ttk.Combobox(row, textvariable=self.source_var, values=list(SOURCES), state="readonly", width=22)
        src.pack(side="left")
        src.bind("<<ComboboxSelected>>", lambda e: self._restart_source())
        row = ttk.Frame(left)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Frame rate", width=14).pack(side="left")
        ttk.Combobox(row, textvariable=self.fps_var, values=("20", "30", "40", "60"), state="readonly",
                     width=5).pack(side="left")

        ttk.Label(mid, text="Peak markers", style="Muted.TLabel").pack(anchor="w")
        self.hold = Slider(mid, "Hold time (s)", 0.0, 15.0, 3.0, fmt="{:.1f}")
        self.hold.pack(anchor="w", pady=2)
        self.fall = Slider(mid, "Fall speed", 0.05, 3.0, 0.5, fmt="{:.2f}")
        self.fall.pack(anchor="w", pady=2)
        ttk.Checkbutton(mid, text="Hold until pushed up or reset", variable=self.infinite_var).pack(anchor="w", pady=2)
        self.peak_colour = ColorField(mid, "Peak colour", "#ffffff")
        self.peak_colour.pack(anchor="w", pady=2)
        self.thick = Slider(mid, "Marker height", 1, 4, 2, integer=True)
        self.thick.pack(anchor="w", pady=2)
        ttk.Button(mid, text="Reset peaks", command=self.peaks.reset).pack(anchor="w", pady=4)

        ttk.Label(right, text="Response", style="Muted.TLabel").pack(anchor="w")
        s_lo, s_hi, s_start = self.SENS_SPEC
        self.sens = Slider(right, "Sensitivity", s_lo, s_hi, s_start)
        self.sens.pack(anchor="w", pady=2)
        self.smooth = Slider(right, "Smoothing", 0.04, 0.8, 0.2)
        self.smooth.pack(anchor="w", pady=2)
        self.range_db = Slider(right, "Dynamic range", 30, 90, 60, fmt="{:.0f} dB")
        self.range_db.pack(anchor="w", pady=2)
        self.normalise_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(right, text="Normalise (auto level)", variable=self.normalise_var).pack(anchor="w", pady=2)
        ttk.Label(right, text="Radial", style="Muted.TLabel").pack(anchor="w", pady=(8, 0))
        self.ring = Slider(right, "Bass ring", 0.5, 8.0, 1.6)
        self.ring.pack(anchor="w", pady=2)
        self.line_smooth = Slider(right, "Line smoothness", 0.0, 1.0, 0.5)
        self.line_smooth.pack(anchor="w", pady=2)
        self.source_note = ttk.Label(right, text="", style="Muted.TLabel", wraplength=250, justify="left")
        self.source_note.pack(anchor="w", pady=6)
        return f

    def _bars_changed(self):
        n = self.bars.get()
        self.peaks.resize(n)
        if self.analyser is not None:
            self.analyser.set_bands(n)
        self.palette_n = 0

    def _start_source(self):
        kind = SOURCES.get(self.source_var.get(), "loopback")
        self.source = make_source(kind)
        self.analyser = Analyser(self.source.rate, bands=self.bars.get())
        note = self.source.name
        if getattr(self.source, "error", ""):
            note += "\n" + self.source.error.split("(")[0].strip()
        self.source_note.configure(text="Source: " + note)

    def _stop_source(self):
        if self.source is not None:
            self.source.stop()
        self.source = None
        self.analyser = None

    def _restart_source(self):
        self._stop_source()
        self._start_source()

    def activate(self):
        self._start_source()
        self.accum = 0.0
        self.display.clear((0, 0, 0))
        self.display.flush()

    def deactivate(self):
        self._stop_source()

    def _ensure_palette(self, n):
        if self.palette_n != n:
            self.palette = [colors.rainbow_rgb(i / max(1, n - 1)) for i in range(n)]
            self.palette_n = n

    def _bar_colour(self, i, level, mode):
        if mode == colors.MODE_RAINBOW:
            return self.palette[i]
        return self.fixed.get()

    def tick(self, dt):
        if self.source is None or self.analyser is None:
            return
        interval = 1.0 / float(self.fps_var.get())
        self.accum += dt
        if self.accum < interval:
            return
        step = min(self.accum, 0.1)
        self.accum = 0.0
        self._apply_response()
        samples = self.source.read(self.analyser.fft_size)
        levels = self.analyser.process(samples, step)
        self.peaks.hold_seconds = self.hold.get()
        self.peaks.fall_per_second = self.fall.get()
        self.peaks.infinite = self.infinite_var.get()
        peaks = self.peaks.update(levels, step)
        self.last_levels = levels
        self.render(self.style_var.get(), levels, peaks, samples, step)

    def _apply_response(self):
        self.analyser.sensitivity = self.sens.get()
        self.analyser.release_tau = self.smooth.get()
        self.analyser.range_db = self.range_db.get()
        self.analyser.normalise = self.normalise_var.get()

    def render(self, style, levels, peaks, samples, step):
        if style in (RADIAL_WAVE, RADIAL):
            self._render_radial(levels, peaks, samples, step, style == RADIAL_WAVE)
        elif style == "Oscilloscope":
            self._render_scope(samples)
        elif style == "Mirrored bars":
            self._render_bars(levels, peaks, mirrored=True)
        else:
            self._render_bars(levels, peaks, mirrored=False)

    def _layout(self, n):
        gap = 1 if n < 40 else 0
        bw = max(1, (W + gap) // n - gap)
        total = n * bw + (n - 1) * gap
        return gap, bw, (W - total) // 2

    def _render_bars(self, levels, peaks, mirrored):
        n = len(levels)
        self._ensure_palette(n)
        mode = COLOUR_MODES[self.colour_var.get()]
        gap, bw, x0 = self._layout(n)
        thk = self.thick.get()
        peak_rgb = self.peak_colour.get()
        rects = []
        marks = []
        half = H // 2
        for i in range(n):
            x = x0 + i * (bw + gap)
            col = self._bar_colour(i, float(levels[i]), mode)
            if mirrored:
                hh = int(round(levels[i] * half))
                ph = int(round(peaks[i] * half))
                if hh > 0:
                    rects.append((x, half - hh, bw, hh, col))
                    rects.append((x, half, bw, hh, col))
                if ph > 0:
                    marks.append((x, half - ph, bw, thk, peak_rgb))
                    marks.append((x, half + ph - thk, bw, thk, peak_rgb))
            else:
                h = int(round(levels[i] * H))
                ph = int(round(peaks[i] * H))
                if h > 0:
                    rects.append((x, H - h, bw, h, col))
                if ph > 0:
                    marks.append((x, H - ph, bw, thk, peak_rgb))
        self.display.clear((0, 0, 0))
        self.display.rects(rects)
        self.display.rects(marks)
        self.display.flush(realtime=True)

    def _render_scope(self, samples):
        x = np.asarray(samples, dtype=float)
        idx = np.linspace(0, len(x) - 1, W)
        ys = np.interp(idx, np.arange(len(x)), x)
        gain = self.sens.get() * 1.6
        py = np.clip(H / 2 - ys * gain * (H / 2), 0, H - 1).astype(int)
        mode = COLOUR_MODES[self.colour_var.get()]
        segs = []
        for i in range(W - 1):
            if mode == colors.MODE_RAINBOW:
                col = colors.rainbow_rgb(i / (W - 1))
            else:
                col = self.fixed.get()
            segs.append((i, int(py[i]), i + 1, int(py[i + 1]), col))
        self.display.clear((0, 0, 0))
        self.display.lines(segs)
        self.display.flush(realtime=True)

    # ---- radial styles -------------------------------------------------
    def _ring_colour(self, t, level, mode):
        if mode == colors.MODE_RAINBOW:
            return colors.rainbow_rgb(t % 1.0)
        return self.fixed.get()

    @staticmethod
    def _towards_red(rgb, f):
        return (int(rgb[0] + (255 - rgb[0]) * f), int(rgb[1] * (1 - f)), int(rgb[2] * (1 - f)))

    def _render_radial(self, levels, peaks, samples, step, with_wave):
        n = len(levels)
        mode = COLOUR_MODES[self.colour_var.get()]
        peak_rgb = self.peak_colour.get()
        span = R_MAX - R_IN
        segs, dots = [], []
        # spectrum spokes, starting at 12 o'clock, clockwise; fade back to red at the tips
        for i in range(n):
            a = -np.pi / 2 + 2 * np.pi * (i + 0.5) / n
            ca, sa = np.cos(a), np.sin(a)
            length = float(levels[i]) * span
            base = self._ring_colour((i + 0.5) / n, float(levels[i]), mode)
            if length >= 1:
                steps = max(1, int(length // 4) + 1)
                for k in range(steps):
                    r0 = R_IN + length * k / steps
                    r1 = R_IN + length * (k + 1) / steps
                    col = self._towards_red(base, BACK * (k + 0.5) / steps) if mode == colors.MODE_RAINBOW else base
                    segs.append((CX + ca * r0, CY + sa * r0, CX + ca * r1, CY + sa * r1, col))
            pk = float(peaks[i]) * span
            if pk >= 1 and self.infinite_var.get():
                dots.append((round(CX + ca * (R_IN + pk)), round(CY + sa * (R_IN + pk)), peak_rgb))
        # bass / kick ring keeps the circle's colours as it expands
        k = max(1, n // 8)
        bass = float(np.mean(levels[:k] if k else levels))
        self.bass_env = max(bass, self.bass_env - 3.0 * step)
        gain = self.ring.get()
        rb = min(R_MAX, 2.0 + self.bass_env * gain * (R_IN - 2) / 1.6)
        m = max(24, int(2 * np.pi * rb))
        ring = []
        for j in range(m):
            a0 = 2 * np.pi * j / m - np.pi / 2
            a1 = 2 * np.pi * (j + 1) / m - np.pi / 2
            col = self._ring_colour((j + 0.5) / m, self.bass_env, mode)
            ring.append((CX + rb * np.cos(a0), CY + rb * np.sin(a0), CX + rb * np.cos(a1), CY + rb * np.sin(a1), col))
        wave = self._wave_segments(samples, mode) if with_wave else []
        self.display.clear((0, 0, 0))
        self.display.lines(segs)
        self.display.lines(ring)
        self.display.lines(wave)
        self.display.pixels(dots)
        self.display.flush(realtime=True)

    def _wave_segments(self, samples, mode):
        half = R_IN - 3
        npts = 2 * half + 1
        x = np.asarray(samples, dtype=float)[-1024:]
        if len(x) < 8:
            return []
        ys = np.interp(np.linspace(0, len(x) - 1, npts), np.arange(len(x)), x)
        sm = self.line_smooth.get()
        if sm > 0.01:                       # box filter then blend with last frame
            w = 1 + 2 * int(sm * 2)
            ys = np.convolve(np.pad(ys, w // 2, mode="edge"), np.ones(w) / w, mode="valid")
            if self.wave_prev is not None and len(self.wave_prev) == npts:
                ys = self.wave_prev * sm * 0.6 + ys * (1 - sm * 0.6)
        self.wave_prev = ys
        peak = float(np.max(np.abs(ys))) if len(ys) else 0.0
        self.wave_ref = max(peak, self.wave_ref * 0.995, 0.02)   # slow auto-gain: follows the drone
        amp = (half * 0.8) / self.wave_ref * min(1.0, self.sens.get())
        py = np.clip(CY - ys * amp, CY - half, CY + half)
        segs = []
        for i in range(npts - 1):
            t = i / (npts - 2)
            col = self._ring_colour(t, abs(ys[i]) / self.wave_ref, mode)
            segs.append((CX - half + i, py[i], CX - half + i + 1, py[i + 1], col))
        return segs
