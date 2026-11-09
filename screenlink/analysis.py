import numpy as np


class Analyser:
    def __init__(self, rate, bands=32, fft_size=2048, fmin=40.0, fmax=16000.0):
        self.rate = rate
        self.fft_size = fft_size
        self.fmin = fmin
        self.fmax = fmax
        self.sensitivity = 1.0
        self.range_db = 60.0
        self.attack_tau = 0.03
        self.release_tau = 0.20
        self.floor_ref_db = -45.0
        self.ref_decay_db = 6.0
        self.normalise = True
        self.fixed_ref_db = -6.0
        self.window = np.hanning(fft_size)
        self.freqs = np.fft.rfftfreq(fft_size, 1.0 / rate)
        self.ref = self.floor_ref_db
        self.set_bands(bands)

    def set_bands(self, bands):
        self.bands = bands
        top = min(self.fmax, self.rate / 2.0 * 0.95)
        edges = np.geomspace(self.fmin, top, bands + 1)
        idx = np.searchsorted(self.freqs, edges)
        self.lo = np.clip(idx[:-1], 1, len(self.freqs) - 2)
        self.hi = np.maximum(idx[1:], self.lo + 1)
        centres = np.sqrt(edges[:-1] * edges[1:])
        self.tilt_db = 3.0 * np.log2(centres / 1000.0)
        self.level = np.zeros(bands)

    def spectrum_db(self, samples):
        x = np.asarray(samples, dtype=np.float64)
        if len(x) < self.fft_size:
            x = np.concatenate([np.zeros(self.fft_size - len(x)), x])
        else:
            x = x[-self.fft_size:]
        mags = np.abs(np.fft.rfft(x * self.window)) / (self.fft_size / 4.0)
        vals = np.array([mags[lo:hi].max() for lo, hi in zip(self.lo, self.hi)])
        return 20.0 * np.log10(vals * self.sensitivity + 1e-9) + self.tilt_db

    def process(self, samples, dt):
        db = self.spectrum_db(samples)
        loudest = float(db.max())
        if self.normalise:
            self.ref = max(self.ref - self.ref_decay_db * dt, loudest, self.floor_ref_db)
        else:
            self.ref = self.fixed_ref_db
        target = np.clip((db - (self.ref - self.range_db)) / self.range_db, 0.0, 1.0)
        rising = target > self.level
        tau = np.where(rising, self.attack_tau, self.release_tau)
        alpha = 1.0 - np.exp(-dt / tau)
        self.level = self.level + (target - self.level) * alpha
        return self.level
