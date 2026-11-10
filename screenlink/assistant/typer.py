import bisect
import random

from .. import fonts

SAMPLE = "the quick brown fox jumps over a lazy dog and then keeps on running far away "


class TypeSchedule:
    def __init__(self, text, cps, seed=7):
        rng = random.Random(seed)
        base = 1.0 / max(1.0, float(cps))
        self.times = []
        t = 0.0
        for ch in text:
            step = base * rng.uniform(0.6, 1.5)
            if ch in ".!?":
                step += 0.22
            elif ch in ",;:":
                step += 0.1
            elif ch == "\n":
                step += 0.15
            elif ch == " " and rng.random() < 0.06:
                step += base * 2.5
            t += step
            self.times.append(t)
        self.total = t
        self.size = len(text)

    def count(self, elapsed):
        return bisect.bisect_right(self.times, elapsed)


def capacity(font, margin=2, spacing=2, top=0):
    text = SAMPLE * 80
    return max(8, int(fonts.fitting_prefix(text, font, margin, spacing, top) * 0.92))


def fit_reply(text, font, margin=2, spacing=2, top=0):
    text = text.strip()
    lines, rows = fonts.layout(text, font, margin, spacing, top)
    if len(lines) <= rows:
        return text
    n = fonts.fitting_prefix(text, font, margin, spacing, top)
    cut = text[:n]
    space = cut.rfind(" ")
    if space > n * 0.6:
        cut = cut[:space]
    cut = cut.rstrip(" ,;:-")
    while cut:
        trial = cut + "..."
        got, rws = fonts.layout(trial, font, margin, spacing, top)
        if len(got) <= rws:
            return trial
        cut = cut[:-1].rstrip(" ,;:-")
    return "..."
