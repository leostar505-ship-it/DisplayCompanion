import bisect
import math
import os

from PIL import Image, ImageDraw, ImageFont

ORANGE = (255, 122, 26)
DARK = (28, 28, 34)
CARD = (28, 28, 34)
EDGE = (44, 44, 54)
FG = (244, 244, 248)
SUB = (160, 160, 176)
KEY = (1, 1, 1)
CARD_W = 380
CARD_H = 100
ICON = 76
SS = 3
U = 1.72

KINDS = {
    "listening": ("Listening...", "Go ahead, I'm all ears"),
    "screenshot": ("Screenshot taken", "Sending your screen to Claude"),
    "thinking": ("Thinking...", "Hang on a second"),
    "responding": ("Responding", "Writing your answer"),
    "done": ("Done", "Reply is on your display"),
    "error": ("Error", "Please try again"),
    "nevermind": ("Never mind", "Nothing was sent"),
}

NEVERMIND_HOLD = 0.9
NEVERMIND_FLAT = 1.8
NEVERMIND_SWAP = 0.0


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def bump(t, a, b):
    return smooth((t - a) / (b - a))


def _font_paths():
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    options = []
    if windir:
        fonts = os.path.join(windir, "Fonts")
        options.append((os.path.join(fonts, "seguisb.ttf"), os.path.join(fonts, "segoeui.ttf")))
        options.append((os.path.join(fonts, "arialbd.ttf"), os.path.join(fonts, "arial.ttf")))
    options.append(("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    for bold, regular in options:
        if os.path.exists(bold) and os.path.exists(regular):
            return bold, regular
    return None, None


def _font(path, size):
    size = max(6, int(size))
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


class Painter:
    def __init__(self, size, ratio):
        self.size = size
        self.ratio = ratio
        self.u = U * ratio
        self.cx = ICON * ratio / 2.0
        self.cy = ICON * ratio / 2.0
        self.img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def layer(self):
        return Image.new("RGBA", (self.size, self.size), (0, 0, 0, 0))

    def dot(self, d, x, y, r, fill):
        d.ellipse((x - r, y - r, x + r, y + r), fill=fill)

    def stroke(self, d, pts, width, fill, closed=False):
        if len(pts) < 2:
            if pts:
                self.dot(d, pts[0][0], pts[0][1], width / 2.0, fill)
            return
        seq = list(pts) + ([pts[0]] if closed else [])
        d.line(seq, fill=fill, width=max(1, int(round(width))), joint="curve")
        r = width / 2.0
        for x, y in (seq if closed else (seq[0], seq[-1])):
            self.dot(d, x, y, r, fill)

    def mix(self, layer, alpha):
        if alpha < 1.0:
            a = layer.getchannel("A").point(lambda v: int(v * max(0.0, alpha)))
            layer.putalpha(a)
        self.img.alpha_composite(layer)

    def base(self):
        self.d.ellipse((self.cx - 36 * self.ratio, self.cy - 36 * self.ratio,
                        self.cx + 36 * self.ratio, self.cy + 36 * self.ratio), fill=ORANGE + (255,))

    def P(self, px, py):
        return (self.cx + px * self.u, self.cy + py * self.u)


def paint_listening(p, now):
    pts = []
    for i in range(61):
        px = -14 + i * 0.5
        env = math.sin(i / 60.0 * math.pi)
        py = math.sin(px * 0.55 - now * 2 * math.pi) * 5.6 * env
        pts.append(p.P(px, py))
    p.stroke(p.d, pts, 3 * p.u, DARK + (255,))


def paint_thinking(p, now):
    for j in range(3):
        dy = 5 * math.sin(now * 6 - j * 0.9)
        x, y = p.P((j - 1) * 11, dy)
        p.dot(p.d, x, y, 3.4 * p.u, DARK + (255,))


def paint_responding(p, now):
    phase = (now * 0.8) % 1
    grow = min(1.0, phase / 0.7)
    left = -14.0
    length = 24.0 * grow
    if length > 0.6:
        steps = max(3, int(length * 2))
        pts = []
        for n in range(steps + 1):
            px = left + length * n / steps
            py = math.sin((px - left) / 3.2) * 2.6 * min(1.0, (px - left) / 6.0)
            pts.append(p.P(px, py))
        p.stroke(p.d, pts, 5.2 * p.u, DARK + (255,))
    if phase < 0.7 or int(now * 4) % 2 == 0:
        x = left + length + 5
        p.stroke(p.d, [p.P(x, -8), p.P(x, 8)], 2.8 * p.u, DARK + (255,))


def check_points(t, pts, total_parts):
    first = total_parts[0]
    total = first + total_parts[1]
    drawn = smooth(t) * total
    out = [pts[0]]
    if drawn <= first:
        f = drawn / first
        out.append((pts[0][0] + (pts[1][0] - pts[0][0]) * f, pts[0][1] + (pts[1][1] - pts[0][1]) * f))
    else:
        out.append(pts[1])
        f = (drawn - first) / total_parts[1]
        out.append((pts[1][0] + (pts[2][0] - pts[1][0]) * f, pts[1][1] + (pts[2][1] - pts[1][1]) * f))
    return out


def paint_done(p, t):
    pts = [(-10, 1), (-3, 8), (11, -8)]
    parts = (math.hypot(7, 7), math.hypot(14, 16))
    line = check_points(t / 0.5, pts, parts)
    p.stroke(p.d, [p.P(x, y) for x, y in line], 5 * p.u, DARK + (255,))
    if 0.3 < t < 0.9:
        rp = (t - 0.3) / 0.6
        lay = p.layer()
        r = (36 + rp * 2) * p.ratio
        ImageDraw.Draw(lay).ellipse((p.cx - r, p.cy - r, p.cx + r, p.cy + r), outline=ORANGE + (255,),
                                    width=max(1, int(2 * p.ratio)))
        p.mix(lay, 1 - rp)


def paint_nevermind(p, t, now):
    amp = 1.0 - smooth((t - NEVERMIND_HOLD) / NEVERMIND_FLAT)
    pts = []
    for i in range(61):
        px = -14 + i * 0.5
        env = math.sin(i / 60.0 * math.pi)
        py = math.sin(px * 0.55 - now * 2 * math.pi) * 5.6 * env * amp
        pts.append(p.P(px, py))
    p.stroke(p.d, pts, 3 * p.u, DARK + (255,))


def paint_error(p, t):
    lay = p.layer()
    d = ImageDraw.Draw(lay)
    top, bot = -12.0, 1.0
    s0 = smooth((t - 2.6) / 0.5)
    s1 = smooth(t / 0.5)
    if s1 > 0.01 and s0 < 0.97:
        p.stroke(d, [p.P(0, top + (bot - top) * s0), p.P(0, top + (bot - top) * s1)], 6.2 * p.u, DARK + (255,))
    dp = (t - 0.5) / 0.4 if t < 3.1 else 1 - (t - 3.1) / 0.4
    if dp > 0:
        sc = 1.0 if dp >= 1 else (1.3 * smooth(dp / 0.6) if dp < 0.6 else 1.3 - 0.3 * smooth((dp - 0.6) / 0.4))
        x, y = p.P(0, 11.5)
        p.dot(d, x, y, 3.6 * p.u * sc, DARK + (255,))
    er = smooth((t - 2.5) / 1.0)
    if er > 0:
        edge = p.cy + (-18 + 40 * er) * p.u
        fade = 9 * p.u
        alpha = lay.getchannel("A")
        px = alpha.load()
        for y in range(p.size):
            if y > edge + p.u:
                continue
            keep = 0.0 if y <= edge - fade else min(1.0, max(0.0, (y - (edge - fade)) / (fade + p.u)))
            if keep >= 1.0:
                continue
            for x in range(p.size):
                v = px[x, y]
                if v:
                    px[x, y] = int(v * keep)
        lay.putalpha(alpha)
    p.img.alpha_composite(lay)


def rounded_path(cx, cy, half, r, steps=14):
    r = max(0.001, min(r, half))
    x0, y0, x1, y1 = cx - half, cy - half, cx + half, cy + half
    pts = [(x0 + r, y0), (x1 - r, y0)]
    corners = [((x1 - r, y0 + r), -90), ((x1 - r, y1 - r), 0), ((x0 + r, y1 - r), 90), ((x0 + r, y0 + r), 180)]
    edges = [(x1, y1 - r), (x0 + r, y1), (x0, y0 + r), (x0 + r, y0)]
    for k, ((ax, ay), start) in enumerate(corners):
        for s in range(1, steps + 1):
            ang = math.radians(start + 90.0 * s / steps)
            pts.append((ax + r * math.cos(ang), ay + r * math.sin(ang)))
        pts.append(edges[k])
    cleaned = [pts[0]]
    for pt in pts[1:]:
        if math.hypot(pt[0] - cleaned[-1][0], pt[1] - cleaned[-1][1]) > 1e-6:
            cleaned.append(pt)
    if math.hypot(cleaned[0][0] - cleaned[-1][0], cleaned[0][1] - cleaned[-1][1]) < 1e-6:
        cleaned.pop()
    return cleaned


class ClosedPath:
    def __init__(self, pts):
        self.pts = pts + [pts[0]]
        self.cum = [0.0]
        for a, b in zip(self.pts, self.pts[1:]):
            self.cum.append(self.cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        self.length = self.cum[-1]

    def at(self, s):
        s %= self.length
        i = max(1, bisect.bisect_left(self.cum, s))
        i = min(i, len(self.pts) - 1)
        seg = self.cum[i] - self.cum[i - 1]
        f = 0.0 if seg <= 0 else (s - self.cum[i - 1]) / seg
        a, b = self.pts[i - 1], self.pts[i]
        return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)


def paint_screenshot(p, t):
    morph = bump(t, 2.0, 2.5)
    half = 12 * p.u
    r = (12 * (1 - morph) + 4 * morph) * p.u
    gap = 0.4 * (1 - morph * morph)
    path = ClosedPath(rounded_path(p.cx, p.cy, half, r))
    width = 3 * p.u
    if gap > 0.01:
        per = path.length / 6.0
        shift = path.length * t * 0.55
        dash = per * (1 - gap)
        n = max(4, int(dash / (p.ratio * 0.8)))
        for i in range(6):
            start = i * per + shift
            pts = [path.at(start + dash * k / n) for k in range(n + 1)]
            p.stroke(p.d, pts, width, DARK + (255,))
    else:
        p.stroke(p.d, path.pts[:-1], width, DARK + (255,), closed=True)
    q = (t - 3.2) / 1.1
    if 0 < q < 1:
        ay = 7 - 14 * smooth(q)
        alpha = q / 0.15 if q < 0.15 else ((1 - q) / 0.2 if q > 0.8 else 1.0)
        lay = p.layer()
        d = ImageDraw.Draw(lay)
        p.stroke(d, [p.P(0, ay + 4), p.P(0, ay - 4)], 3 * p.u, DARK + (255,))
        p.stroke(d, [p.P(-4, ay - 1), p.P(0, ay - 5), p.P(4, ay - 1)], 3 * p.u, DARK + (255,))
        p.mix(lay, alpha)
    k = (t - 5.0) / 0.5
    if k > 0:
        pts = [(-6, 0.5), (-1.5, 5), (6.5, -5)]
        parts = (math.hypot(4.5, 4.5), math.hypot(8, 10))
        line = check_points(k, pts, parts)
        p.stroke(p.d, [p.P(x, y) for x, y in line], 3.4 * p.u, DARK + (255,))


def icon_image(kind, t, now, scale, shot_speed=1.0):
    out = max(8, int(round(ICON * scale)))
    ratio = out * SS / float(ICON)
    p = Painter(out * SS, ratio)
    p.base()
    if kind == "listening":
        paint_listening(p, now)
    elif kind == "screenshot":
        paint_screenshot(p, t * shot_speed)
    elif kind == "thinking":
        paint_thinking(p, now)
    elif kind == "responding":
        paint_responding(p, now)
    elif kind == "done":
        paint_done(p, t)
    elif kind == "error":
        paint_error(p, t)
    elif kind == "nevermind":
        paint_nevermind(p, t, now)
    return p.img.resize((out, out), Image.LANCZOS)


class Card:
    def __init__(self, scale=1.5):
        self.scale = scale
        self.w = int(round(CARD_W * scale))
        self.h = int(round(CARD_H * scale))
        bold, regular = _font_paths()
        self.title_font = _font(bold, 19 * scale)
        self.sub_font = _font(regular, 14 * scale)
        self.base = self._base()
        self.text_cache = {}

    def _base(self):
        s = self.scale
        big = Image.new("RGB", (self.w * SS, self.h * SS), KEY)
        d = ImageDraw.Draw(big)
        k = s * SS
        d.rounded_rectangle((0, 0, self.w * SS - 1, self.h * SS - 1), radius=22 * k, fill=EDGE)
        d.rounded_rectangle((2 * k, 2 * k, self.w * SS - 1 - 2 * k, self.h * SS - 1 - 2 * k), radius=20 * k, fill=CARD)
        d.rounded_rectangle((16 * k, 24 * k, 22 * k, 76 * k), radius=3 * k, fill=ORANGE)
        return big.resize((self.w, self.h), Image.LANCZOS)

    def _text(self, title, sub):
        key = (title, sub)
        if key in self.text_cache:
            return self.text_cache[key]
        s = self.scale
        layer = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        x = int(126 * s)
        max_w = int((CARD_W - 18) * s) - x
        sub_fit = sub
        while sub_fit and d.textlength(sub_fit, font=self.sub_font) > max_w:
            sub_fit = sub_fit[:-1]
        if sub_fit != sub:
            sub_fit = sub_fit.rstrip() + "..."
        d.text((x, int(29 * s)), title, font=self.title_font, fill=FG + (255,))
        d.text((x, int(29 * s + 25 * s)), sub_fit, font=self.sub_font, fill=SUB + (255,))
        self.text_cache[key] = layer
        if len(self.text_cache) > 40:
            self.text_cache.pop(next(iter(self.text_cache)))
        return layer

    def render(self, kind, t, now, frac=None, shot_speed=1.0, title=None, sub=None):
        base_title, base_sub = KINDS[kind]
        if kind == "nevermind" and t < NEVERMIND_SWAP:
            base_title, base_sub = KINDS["listening"]
        img = self.base.copy().convert("RGBA")
        s = self.scale
        icon = icon_image(kind, t, now, s, shot_speed)
        img.alpha_composite(icon, (int(36 * s), int(12 * s)))
        img.alpha_composite(self._text(title or base_title, sub or base_sub))
        if frac is not None and frac > 0:
            d = ImageDraw.Draw(img)
            width = (CARD_W - 44) * s * min(1.0, frac)
            if width > 2:
                d.rounded_rectangle((22 * s, self.h - 7 * s - 3 * s, 22 * s + width, self.h - 7 * s),
                                    radius=1.5 * s, fill=ORANGE + (255,))
        return img.convert("RGB")
