import math
from collections import namedtuple

from . import colors
from .analysis import BANDS

Prim = namedtuple("Prim", "kind a b c d w rgb alpha")


def line(x0, y0, x1, y1, width, rgb, alpha=1.0):
    return Prim("line", x0, y0, x1, y1, width, rgb, alpha)


def rect(x0, y0, x1, y1, rgb):
    return Prim("rect", x0, y0, x1, y1, 0.0, rgb, 1.0)


def ring(cx, cy, radius, width, rgb, alpha):
    return Prim("ring", cx, cy, radius, 0.0, width, rgb, alpha)


SHELLS = 6
BAR_SHELLS = 8
RING_SEGS = 72


def height_gain(look):
    return max(0.0, look.sensitivity) / 1.6


class Look:
    def __init__(self, mode, fixed, sensitivity, ring=1.0, smooth=0.5):
        self.smooth = smooth
        self.mode = mode
        self.fixed = fixed
        self.sensitivity = sensitivity
        self.ring = ring


class RadialVisual:
    def __init__(self):
        self.pulse = 0.0
        self.ring_r = 0.0
        self.ring_a = 0.0
        self.ring_v = 0.0

    def frame(self, width, height, dt, an, look, pixel):
        cx = width / 2.0
        cy = height / 2.0
        m = float(min(width, height))
        self.pulse = max(self.pulse * 0.85 ** (dt * 60.0), an.bass_now)
        r0 = m * 0.2 + self.pulse * m * 0.08
        max_len = m * 0.28
        if pixel:
            bar_w = max(1.0, float(round(m / 64.0)))
            ring_w = max(1.0, float(round(min(look.ring, 3.0))))
        else:
            bar_w = max(1.0, m / 64.0)
            ring_w = max(1.0, m / 128.0) * (0.6 + 0.4 * min(look.ring, 3.0))
        min_len = bar_w
        gain = height_gain(look)
        prims = []
        rainbow = look.mode == colors.MODE_RAINBOW
        cross = m * 0.2
        far = width / 2.0
        for i in range(BANDS):
            length = min(1.0, an.vals[i] * gain) * max_len + min_len
            ang = (i + 0.5) / BANDS * math.pi - math.pi / 2.0
            cos_a = math.cos(ang)
            sin_a = math.sin(ang)
            if rainbow:
                rgb = colors.wave_rgb(abs(cos_a) * cross, cross, far)
                ya = cy + sin_a * r0
                yb = cy + sin_a * (r0 + length)
                prims.append(line(cx - cos_a * r0, ya, cx - cos_a * (r0 + length), yb, bar_w, rgb))
                prims.append(line(cx + cos_a * r0, ya, cx + cos_a * (r0 + length), yb, bar_w, rgb))
            else:
                y0 = cy + sin_a * r0
                y1 = cy + sin_a * (r0 + length)
                rgb = colors.bar_rgb(look.mode, i, BANDS, an.vals[i], look.sensitivity, look.fixed)
                prims.append(line(cx - cos_a * r0, y0, cx - cos_a * (r0 + length), y1, bar_w, rgb))
                prims.append(line(cx + cos_a * r0, y0, cx + cos_a * (r0 + length), y1, bar_w, rgb))
        if an.beat:
            self.ring_r = r0
            self.ring_a = 1.0
            self.ring_v = 0.5 + an.bass_now * look.sensitivity
        elif self.ring_a > 0.0:
            self.ring_r += m * 1.8 * dt
            self.ring_a -= 3.0 * dt / math.sqrt(max(0.25, look.ring))
        if self.ring_a > 0.0:
            if rainbow:
                n = RING_SEGS
                for j in range(n):
                    a0 = 2.0 * math.pi * j / n
                    a1 = 2.0 * math.pi * (j + 1) / n
                    rgb = colors.wave_rgb(cross * math.cos((a0 + a1) / 2.0), cross, far)
                    prims.append(line(cx + self.ring_r * math.cos(a0), cy + self.ring_r * math.sin(a0),
                                      cx + self.ring_r * math.cos(a1), cy + self.ring_r * math.sin(a1),
                                      ring_w, rgb, self.ring_a))
            else:
                base = colors.ring_rgb(look.mode, self.ring_v, look.fixed)
                prims.append(ring(cx, cy, self.ring_r, ring_w, base, self.ring_a))
        return prims


class BarsVisual:
    def __init__(self):
        self.peaks = [0.0] * BANDS
        self.held = [0.0] * BANDS

    def frame(self, width, height, dt, an, look, pixel):
        hold = float(getattr(look, "hold", 0.0))
        gain = height_gain(look)
        mid = height / 2.0
        bw = width / BANDS
        fall = height * 0.72 * dt
        if pixel:
            bar_w = max(1.0, bw - 1.0)
            dot = max(1.0, float(round(height / 100.0)))
        else:
            bar_w = bw * 0.76
            dot = max(2.0, height / 64.0)
        offset = 0.0 if pixel else bw * 0.12
        bars = []
        tops = []
        bottoms = []
        white = (255, 255, 255)
        for i in range(BANDS):
            h = min(1.0, an.vals[i] * gain) * (mid - 1.0)
            if h >= self.peaks[i]:
                self.held[i] = 0.0
                peak = h
            else:
                self.held[i] += dt
                peak = self.peaks[i] if self.held[i] < hold else max(h, self.peaks[i] - fall)
            self.peaks[i] = peak
            x0 = i * bw + offset
            x1 = x0 + bar_w
            if look.mode == colors.MODE_RAINBOW:
                rgb = colors.spectrum_rgb(i, BANDS)
                bars.append(rect(x0, mid - h, x1, mid + h + 1.0, rgb))
            else:
                rgb = colors.bar_rgb(look.mode, i, BANDS, an.vals[i], look.sensitivity, look.fixed)
                bars.append(rect(x0, mid - h, x1, mid + h + 1.0, rgb))
            tops.append(rect(x0, mid - peak - dot - 1.0, x1, mid - peak - 1.0, white))
            bottoms.append(rect(x0, mid + peak + 1.0, x1, mid + peak + dot + 1.0, white))
        return bars + tops + bottoms


class WaveRadialVisual(RadialVisual):
    def __init__(self):
        super().__init__()
        self.log_f = None
        self.amp = 0.0
        self.peak = 0.02
        self.phase = 0.0

    def wave_prims(self, width, height, dt, an, look, pixel):
        dt = min(max(dt, 1e-3), 0.1)
        steps = dt * 60.0
        smooth = min(1.0, max(0.0, look.smooth))
        keep = (smooth * 0.92) ** steps
        target = math.log2(max(an.drone_hz, 20.0))
        amp = an.drone_mag / 0.21
        if self.log_f is None:
            self.log_f = target
            self.amp = amp
        self.log_f = keep * self.log_f + (1.0 - keep) * target
        self.amp = keep * self.amp + (1.0 - keep) * amp
        self.peak = max(self.amp, self.peak * 0.995**steps, 0.02)
        level = min(1.0, self.amp / self.peak)
        freq = 2.0**self.log_f
        cycles = min(12.0, max(1.0, 1.0 + 1.6 * (self.log_f - math.log2(40.0))))
        self.phase = (self.phase + 2.0 * math.pi * min(6.0, max(0.4, freq / 80.0)) * dt) % (2.0 * math.pi)
        n = int(min(240, max(96, cycles * 14)))
        if pixel:
            n = int(max(16, min(n, width)))
        m = float(min(width, height))
        amp_px = m * 0.16 * level
        cy = height / 2.0
        stroke = 1.0 if pixel else max(1.5, m / 200.0)
        cross = m * 0.2
        half = width / 2.0
        ys = []
        for i in range(n):
            u = i / (n - 1)
            ys.append(math.sin(2.0 * math.pi * cycles * u - self.phase))
        prims = []
        for i in range(n - 1):
            x0 = i / (n - 1) * (width - 1)
            x1 = (i + 1) / (n - 1) * (width - 1)
            y0 = cy - ys[i] * amp_px
            y1 = cy - ys[i + 1] * amp_px
            if look.mode == colors.MODE_RAINBOW:
                rgb = colors.wave_rgb((x0 + x1) / 2.0 - width / 2.0, cross, half)
            else:
                rgb = colors.bar_rgb(look.mode, i, n - 1, level * abs(ys[i]), look.sensitivity, look.fixed)
            prims.append(line(x0, y0, x1, y1, stroke, rgb))
        return prims

    def frame(self, width, height, dt, an, look, pixel):
        wave = self.wave_prims(width, height, dt, an, look, pixel)
        return wave + super().frame(width, height, dt, an, look, pixel)


class WaveVisual(WaveRadialVisual):
    """Waveform only: the clean drone sine, no bars or bass ring."""

    def frame(self, width, height, dt, an, look, pixel):
        return self.wave_prims(width, height, dt, an, look, pixel)


VISUALS = {"wave": WaveVisual, "radial_wave": WaveRadialVisual, "radial": RadialVisual, "bars": BarsVisual}
