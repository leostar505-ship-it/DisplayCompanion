import colorsys

import numpy as np

RAINBOW_STOPS = (
    (1.0, 0.0),
    (0.8, 60.0),
    (0.8, 120.0),
    (0.8, 180.0),
    (1.8, 240.0),
    (0.6, 285.0),
    (0.25, 330.0),
)

MODE_RAINBOW = "rainbow"
MODE_LOUDNESS = "loudness"
MODE_FIXED = "fixed"

_LOUDNESS_POINTS = (0.0, 0.25, 0.5, 0.75, 0.9, 1.0)
_LOUDNESS_HUES = (330.0, 285.0, 240.0, 120.0, 60.0, 0.0)


def hsv_rgb(hue, sat=1.0, val=1.0):
    r, g, b = colorsys.hsv_to_rgb((hue % 360.0) / 360.0, sat, val)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def build_rainbow_lut(stops=RAINBOW_STOPS, size=256):
    total = sum(w for w, _ in stops)
    centres = []
    acc = 0.0
    for w, _ in stops:
        centres.append((acc + w / 2.0) / total)
        acc += w
    hues = [h for _, h in stops]
    lut = []
    for i in range(size):
        t = i / (size - 1)
        lut.append(hsv_rgb(float(np.interp(t, centres, hues))))
    return lut


_LUT = build_rainbow_lut()


def rainbow_rgb(t):
    t = min(1.0, max(0.0, float(t)))
    return _LUT[int(round(t * (len(_LUT) - 1)))]


def loudness_rgb(level):
    level = min(1.0, max(0.0, float(level)))
    return hsv_rgb(float(np.interp(level, _LOUDNESS_POINTS, _LOUDNESS_HUES)))


def parse_hex(text):
    s = str(text).strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        return None
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return None


def to_hex(rgb):
    return "#%02x%02x%02x" % tuple(int(v) & 255 for v in rgb)
