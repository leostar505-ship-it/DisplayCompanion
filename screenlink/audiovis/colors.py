import colorsys

MODE_LOUDNESS = "loudness"
MODE_FIXED = "custom"
MODE_RAINBOW = "rainbow"
MODES = (MODE_LOUDNESS, MODE_FIXED, MODE_RAINBOW)

HEX_DIGITS = set("0123456789abcdefABCDEF")


def clamp01(value):
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def hsl_to_rgb(h, s, l):
    r, g, b = colorsys.hls_to_rgb((h % 360.0) / 360.0, l / 100.0, s / 100.0)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def loudness_rgb(value):
    v = clamp01(value)
    return hsl_to_rgb(330.0 * (1.0 - v), 95.0, 52.0 + v * 8.0)


def rainbow_rgb(index, count):
    return hsl_to_rgb(index / count * 300.0, 90.0, 55.0)


# Rainbow tuned in the colour preview: (weight, hue) from the centre to the circle edge.
RAINBOW_STOPS = ((1.0, 0.0), (0.8, 60.0), (0.8, 120.0), (0.8, 180.0), (1.8, 240.0), (0.6, 285.0), (0.25, 330.0))
RAINBOW_BACK = 0.55  # share of the distance outside the circle taken to go from pink back to red


def _rainbow_centres():
    total = sum(w for w, _ in RAINBOW_STOPS)
    acc = 0.0
    out = []
    for w, _ in RAINBOW_STOPS:
        out.append((acc + w / 2.0) / total)
        acc += w
    return out


_CENTRES = _rainbow_centres()


def rainbow_hue(t):
    """Hue for t = distance from the centre as a fraction of the circle radius (0 to 1)."""
    if t <= _CENTRES[0]:
        return RAINBOW_STOPS[0][1]
    for i in range(1, len(_CENTRES)):
        if t <= _CENTRES[i]:
            u = (t - _CENTRES[i - 1]) / (_CENTRES[i] - _CENTRES[i - 1])
            h0 = RAINBOW_STOPS[i - 1][1]
            return h0 + u * (RAINBOW_STOPS[i][1] - h0)
    return RAINBOW_STOPS[-1][1]


def wave_rgb(dx, crossing, half):
    d = abs(dx)
    if d <= crossing:
        hue = rainbow_hue(d / max(crossing, 1e-6))
    else:
        hue = 330.0 + 30.0 * min(1.0, (d - crossing) / max(RAINBOW_BACK * (half - crossing), 1e-6))
    return hsl_to_rgb(hue, 90.0, 55.0)


RING_RAINBOW = hsl_to_rgb(190.0, 90.0, 60.0)


def blend(rgb, alpha):
    a = clamp01(alpha)
    return (int(rgb[0] * a), int(rgb[1] * a), int(rgb[2] * a))


def to_hex(rgb):
    return "#%02x%02x%02x" % (rgb[0], rgb[1], rgb[2])


def parse_hex(text):
    t = text.strip().lstrip("#")
    if len(t) == 3 and all(c in HEX_DIGITS for c in t):
        t = "".join(c * 2 for c in t)
    if len(t) != 6 or any(c not in HEX_DIGITS for c in t):
        return None
    return (int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16))


def bar_rgb(mode, index, count, value, sensitivity, fixed):
    if mode == MODE_FIXED:
        return fixed
    if mode == MODE_RAINBOW:
        return rainbow_rgb(index, count)
    return loudness_rgb(value * sensitivity)


def ring_rgb(mode, scaled_value, fixed):
    if mode == MODE_FIXED:
        return fixed
    if mode == MODE_RAINBOW:
        return RING_RAINBOW
    return loudness_rgb(scaled_value)
