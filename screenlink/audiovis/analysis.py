import math

import numpy as np

FFT_SIZE = 2048
BANDS = 32
MIN_DB = -100.0
MAX_DB = -30.0
SMOOTHING = 0.55
F_MIN = 40.0
F_MAX = 16000.0
BASS_BANDS = 5
TARGET_RATE = 48000
TRIGGERS = {"kick": (40.0, 800.0), "bass": (40.0, 160.0)}
DEFAULT_TRIGGER = "kick"
ONSET_AMP_FLOOR = 1e-4
ONSET_GAP = 0.2
ONSET_FLOOR = 1.5
DRONE_LO = 30.0
DRONE_HI = 4000.0
DRONE_SWITCH = 1.4


def decimation_factor(rate):
    return max(1, int(math.floor(rate / TARGET_RATE + 0.5)))


def band_edges(sample_rate, fft_size=FFT_SIZE, bands=BANDS):
    bin_count = fft_size // 2
    nyq = sample_rate / 2.0
    lo = []
    hi = []
    prev = 1
    for i in range(bands):
        f0 = F_MIN * (F_MAX / F_MIN) ** (i / bands)
        f1 = F_MIN * (F_MAX / F_MIN) ** ((i + 1) / bands)
        a = max(prev, int(math.floor(f0 / nyq * bin_count + 0.5)))
        b = max(a + 1, int(math.floor(f1 / nyq * bin_count + 0.5)))
        a = min(a, bin_count)
        b = min(b, bin_count)
        lo.append(a)
        hi.append(b)
        prev = b
    return np.array(lo, dtype=np.int64), np.array(hi, dtype=np.int64)


def blackman(n):
    k = np.arange(n) / n
    window = 0.42 - 0.5 * np.cos(2.0 * np.pi * k) + 0.08 * np.cos(4.0 * np.pi * k)
    return window.astype(np.float32)


class Analyser:
    def __init__(self, sample_rate=TARGET_RATE):
        self.window = blackman(FFT_SIZE)
        self.smoothed = np.zeros(FFT_SIZE // 2)
        self.avg = np.zeros(BANDS)
        self.bands = np.zeros(BANDS)
        self.vals = np.zeros(BANDS)
        self.bass_avg = 0.0
        self.bass_now = 0.0
        self.level = 0.0
        self.beat = False
        self.last_beat = -1e9
        self.normalise = True
        self.ring_sens = 1.0
        self.trigger = DEFAULT_TRIGGER
        self.wave = np.zeros(FFT_SIZE, dtype=np.float32)
        self.prev_lm = None
        self.flux = 0.0
        self.flux_mean = 0.0
        self.flux_var = 0.0
        self.drone_bin = 0
        self.drone_hz = 0.0
        self.drone_mag = 0.0
        self.rate = 0
        self.lo = None
        self.hi = None
        self.width = None
        self.set_rate(sample_rate)

    def set_rate(self, sample_rate):
        if sample_rate == self.rate:
            return
        self.rate = sample_rate
        self.lo, self.hi = band_edges(sample_rate)
        self.width = np.maximum(self.hi - self.lo, 1)
        bin_hz = sample_rate / FFT_SIZE
        self._set_onset_bins()
        self.dr_a = max(1, int(DRONE_LO / bin_hz))
        self.dr_b = min(FFT_SIZE // 2 - 2, int(DRONE_HI / bin_hz))
        self.prev_lm = None

    def _set_onset_bins(self):
        lo, hi = TRIGGERS.get(self.trigger, TRIGGERS[DEFAULT_TRIGGER])
        bin_hz = self.rate / FFT_SIZE
        self.on_a = max(1, int(lo / bin_hz))
        self.on_b = max(self.on_a + 2, int(hi / bin_hz))
        self.prev_lm = None

    def set_trigger(self, name):
        if name not in TRIGGERS or name == self.trigger:
            return
        self.trigger = name
        self._set_onset_bins()
        self.flux_mean = 0.0
        self.flux_var = 0.0

    def update(self, samples, dt, now):
        dt = min(max(dt, 1e-3), 0.1)
        steps = dt * 60.0
        self.wave = np.asarray(samples, dtype=np.float32)
        spectrum = np.abs(np.fft.rfft(samples * self.window))[: FFT_SIZE // 2] / FFT_SIZE
        k = SMOOTHING**steps
        self.smoothed = k * self.smoothed + (1.0 - k) * spectrum
        db = 20.0 * np.log10(np.maximum(self.smoothed, 1e-10))
        norm = np.clip((db - MIN_DB) / (MAX_DB - MIN_DB), 0.0, 1.0)
        cumulative = np.concatenate(([0.0], np.cumsum(norm)))
        self.bands = (cumulative[self.hi] - cumulative[self.lo]) / self.width
        self.avg += (self.bands - self.avg) * (1.0 - 0.985**steps)
        if self.normalise:
            self.vals = np.clip((self.bands - self.avg * 0.95) * 2.5, 0.0, 1.0)
        else:
            self.vals = self.bands.copy()
        self.level = float(self.bands.mean())
        bass = float(self.bands[:BASS_BANDS].mean())
        self.bass_now = float(self.vals[:BASS_BANDS].mean())
        self.beat = False
        self._onset(spectrum, steps, now)
        self._drone(steps)
        keep = 0.95**steps
        self.bass_avg = self.bass_avg * keep + bass * (1.0 - keep)

    def _onset(self, spectrum, steps, now):
        lm = 20.0 * np.log10(np.maximum(spectrum[self.on_a : self.on_b], ONSET_AMP_FLOOR))
        if self.prev_lm is None or len(self.prev_lm) != len(lm):
            self.prev_lm = lm
            self.flux = 0.0
            return
        self.flux = float(np.maximum(lm - self.prev_lm, 0.0).mean())
        self.prev_lm = lm
        c = 2.4 / max(0.25, float(self.ring_sens))
        threshold = self.flux_mean + c * math.sqrt(max(self.flux_var, 0.0))
        if self.flux > threshold and self.flux > ONSET_FLOOR and now - self.last_beat > ONSET_GAP:
            self.beat = True
            self.last_beat = now
        keep = 0.98**steps
        diff = self.flux - self.flux_mean
        self.flux_mean += diff * (1.0 - keep)
        self.flux_var = keep * (self.flux_var + (1.0 - keep) * diff * diff)

    def _drone(self, steps):
        seg = self.smoothed[self.dr_a : self.dr_b]
        if len(seg) < 3:
            return
        best = int(np.argmax(seg)) + self.dr_a
        cur = self.drone_bin
        if cur < self.dr_a or cur >= self.dr_b or self.smoothed[best] > self.smoothed[cur] * DRONE_SWITCH:
            cur = best
        self.drone_bin = cur
        mag = float(self.smoothed[cur])
        left = math.log(max(float(self.smoothed[cur - 1]), 1e-12))
        mid = math.log(max(mag, 1e-12))
        right = math.log(max(float(self.smoothed[cur + 1]), 1e-12))
        denom = left - 2.0 * mid + right
        shift = 0.5 * (left - right) / denom if denom < -1e-9 else 0.0
        shift = max(-0.5, min(0.5, shift))
        self.drone_hz = (cur + shift) * self.rate / FFT_SIZE
        self.drone_mag = mag
