import numpy as np


class PeakHold:
    def __init__(self, count, hold_seconds=2.0, fall_per_second=0.6, infinite=False):
        self.count = count
        self.hold_seconds = hold_seconds
        self.fall_per_second = fall_per_second
        self.infinite = infinite
        self.peaks = np.zeros(count)
        self.timers = np.zeros(count)

    def resize(self, count):
        if count != self.count:
            self.count = count
            self.peaks = np.zeros(count)
            self.timers = np.zeros(count)

    def reset(self):
        self.peaks[:] = 0.0
        self.timers[:] = 0.0

    def update(self, levels, dt):
        levels = np.clip(np.asarray(levels, dtype=float), 0.0, 1.0)
        pushed = levels >= self.peaks
        self.peaks = np.where(pushed, levels, self.peaks)
        self.timers = np.where(pushed, 0.0, self.timers + dt)
        if not self.infinite:
            falling = self.timers > self.hold_seconds
            fallen = self.peaks - self.fall_per_second * dt
            self.peaks = np.where(falling, np.maximum(fallen, levels), self.peaks)
        return self.peaks
