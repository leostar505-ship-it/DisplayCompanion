import os

from PIL import Image, ImageDraw, ImageFont

from .protocol import HEIGHT, WIDTH

BUILTIN = "Built-in font"

_WINDOWS = [
    ("Segoe UI", "segoeui.ttf"),
    ("Consolas", "consola.ttf"),
    ("Arial", "arial.ttf"),
    ("Arial Black", "ariblk.ttf"),
    ("Calibri", "calibri.ttf"),
    ("Courier New", "cour.ttf"),
    ("Impact", "impact.ttf"),
    ("Verdana", "verdana.ttf"),
    ("Comic Sans MS", "comic.ttf"),
]

_LINUX = [
    ("DejaVu Sans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ("DejaVu Sans Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("DejaVu Sans Mono", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    ("Liberation Sans", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ("Liberation Mono", "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"),
]

_MAC = [
    ("Helvetica", "/System/Library/Fonts/Helvetica.ttc"),
    ("Menlo", "/System/Library/Fonts/Menlo.ttc"),
]


_EMOJI_PATHS = [
    ("win", "seguiemj.ttf"),
    ("noto", "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
    ("noto", "/usr/share/fonts/noto/NotoColorEmoji.ttf"),
    ("apple", "/System/Library/Fonts/Apple Color Emoji.ttc"),
]
_emoji_cache = {}
_emoji_face = {}


def is_emoji_char(ch):
    o = ord(ch)
    return (0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF or 0x2B00 <= o <= 0x2BFF
            or 0x2300 <= o <= 0x23FF or 0x2190 <= o <= 0x21FF or 0x2900 <= o <= 0x297F
            or o in (0x200D, 0xFE0F, 0x20E3, 0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D, 0x3297, 0x3299)
            or 0xE0020 <= o <= 0xE007F)


def has_emoji(text):
    return any(is_emoji_char(c) for c in str(text))


def _emoji_font(strike_hint):
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    for kind, path in _EMOJI_PATHS:
        if kind == "win":
            if not windir:
                continue
            path = os.path.join(windir, "Fonts", path)
        if not os.path.exists(path):
            continue
        strike = {"win": strike_hint, "noto": 109, "apple": 160}[kind]
        key = (path, strike)
        if key not in _emoji_face:
            try:
                _emoji_face[key] = ImageFont.truetype(path, strike)
            except Exception:
                _emoji_face[key] = None
        if _emoji_face[key] is not None:
            return _emoji_face[key]
    return None


def _emoji_image(run, height):
    key = (run, height)
    if key in _emoji_cache:
        return _emoji_cache[key]
    face = _emoji_font(max(48, height * 4))
    img = None
    if face is not None:
        try:
            box = ImageDraw.Draw(Image.new("RGBA", (4, 4))).textbbox((0, 0), run, font=face, embedded_color=True)
            w = max(1, box[2] - box[0])
            h = max(1, box[3] - box[1])
            canvas = Image.new("RGBA", (w + 4, h + 4), (0, 0, 0, 0))
            ImageDraw.Draw(canvas).text((2 - box[0], 2 - box[1]), run, font=face, embedded_color=True)
            canvas = canvas.crop(canvas.getbbox() or (0, 0, 1, 1))
            scale = height / max(1, canvas.height)
            new_w = max(1, int(round(canvas.width * scale)))
            img = canvas.resize((new_w, max(1, height)), Image.LANCZOS)
        except Exception:
            img = None
    if len(_emoji_cache) > 256:
        _emoji_cache.clear()
    _emoji_cache[key] = img
    return img


def _runs(text):
    runs = []
    for ch in text:
        emo = is_emoji_char(ch)
        if runs and runs[-1][0] == emo:
            runs[-1][1] += ch
        else:
            runs.append([emo, ch])
    return runs


def _glyph_height(font):
    probe = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    one = probe.textbbox((0, 0), "Ag", font=font)
    return max(4, one[3] - one[1])


def text_length(probe, text, font):
    if not has_emoji(text):
        return probe.textlength(text, font=font)
    height = _glyph_height(font)
    total = 0.0
    for emo, run in _runs(text):
        if emo:
            img = _emoji_image(run, height)
            if img is not None:
                total += img.width + 1
                continue
        total += probe.textlength(run, font=font)
    return total


def draw_text(img, draw, xy, text, font, fill):
    x, y = xy
    if not has_emoji(text):
        draw.text((x, y), text, fill=fill, font=font)
        return
    height = _glyph_height(font)
    one = draw.textbbox((0, 0), "Ag", font=font)
    for emo, run in _runs(text):
        if emo:
            pic = _emoji_image(run, height)
            if pic is not None:
                img.paste(pic, (int(round(x)), int(round(y + one[1]))), pic)
                x += pic.width + 1
                continue
        draw.text((x, y), run, fill=fill, font=font)
        x += draw.textlength(run, font=font)


def discover_fonts():
    found = {}
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windir:
        for name, fname in _WINDOWS:
            path = os.path.join(windir, "Fonts", fname)
            if os.path.exists(path):
                found[name] = path
    for name, path in _LINUX + _MAC:
        if os.path.exists(path):
            found[name] = path
    found[BUILTIN] = None
    return found


def load_font(path, size):
    size = max(4, int(size))
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def text_size(draw, text, font, spacing=2):
    box = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing)
    return box


def layout(text, font, margin=2, spacing=2, top=0, notch=None):
    probe = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    one = probe.textbbox((0, 0), "Ag", font=font)
    single = one[3] - one[1]
    two = probe.multiline_textbbox((0, 0), "Ag\nAg", font=font, spacing=spacing)
    pitch = max(1, (two[3] - two[1]) - single)
    narrow = None
    if notch:
        count = max(1, -(-(notch[1] - margin) // pitch))
        narrow = (count, WIDTH - margin * 2 - notch[0])
    lines = wrap_text(text, font, WIDTH - margin * 2, narrow)
    avail = HEIGHT - margin * 2 - top
    rows = 0 if avail < single else 1 + (avail - single) // pitch
    return lines, rows


def fitting_prefix(text, font, margin=2, spacing=2, top=0, notch=None):
    lines, rows = layout(text, font, margin, spacing, top, notch)
    if len(lines) <= rows:
        return len(text)
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        got, _ = layout(text[:mid], font, margin, spacing, top, notch)
        if len(got) <= rows:
            lo = mid
        else:
            hi = mid - 1
    return lo


def render_block(text, font, fg, bg, align="center", valign="middle", margin=2, spacing=2, wrap=True, top=0, notch=None):
    img = Image.new("RGB", (WIDTH, HEIGHT), bg)
    draw = ImageDraw.Draw(img)
    if not text:
        return img
    if wrap:
        text = "\n".join(layout(text, font, margin, spacing, top, notch)[0])
    box = text_size(draw, text, font, spacing)
    tw = box[2] - box[0]
    th = box[3] - box[1]
    if align == "left":
        x = margin
    elif align == "right":
        x = WIDTH - tw - margin
    else:
        x = (WIDTH - tw) // 2
    if valign == "top":
        y = margin + top
    elif valign == "bottom":
        y = HEIGHT - th - margin
    else:
        y = (HEIGHT - th) // 2
    if has_emoji(text):
        top, pitch = metrics(font, spacing)
        rows = text.split("\n")
        yy = y
        for row in rows:
            rw = text_length(draw, row, font)
            if align == "left":
                rx = margin
            elif align == "right":
                rx = WIDTH - rw - margin
            else:
                rx = (WIDTH - rw) / 2
            draw_text(img, draw, (rx, yy - top), row, font, fg)
            yy += pitch
        return img
    draw.multiline_text((x - box[0], y - box[1]), text, fill=fg, font=font, spacing=spacing, align=align)
    return img


def render_strip(text, font, fg, bg, pad=WIDTH):
    probe = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    box = probe.textbbox((0, 0), text, font=font)
    tw = box[2] - box[0]
    th = box[3] - box[1]
    img = Image.new("RGB", (tw + pad * 2, HEIGHT), bg)
    ImageDraw.Draw(img).text((pad - box[0], (HEIGHT - th) // 2 - box[1]), text, fill=fg, font=font)
    return img, tw


def fit_size(text, path, lo=6, hi=72, margin=4):
    best = lo
    for size in range(lo, hi + 1):
        font = load_font(path, size)
        lines, rows = layout(text, font, margin // 2)
        widest = max([ImageDraw.Draw(Image.new("RGB", (4, 4))).textlength(l, font=font) for l in lines] or [0])
        if len(lines) <= rows and widest <= WIDTH - margin:
            best = size
        else:
            break
    return best


def wrap_text(text, font, width, narrow=None):
    probe = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    lines = []
    full = width
    for raw in text.split("\n"):
        words = raw.split(" ")
        cur = ""
        for word in words:
            width = narrow[1] if narrow and len(lines) < narrow[0] else full
            trial = word if not cur else cur + " " + word
            if text_length(probe, trial, font) <= width:
                cur = trial
                continue
            if cur:
                lines.append(cur)
            while text_length(probe, word, font) > width and len(word) > 1:
                cut = len(word)
                while cut > 1 and text_length(probe, word[:cut], font) > width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            cur = word
        lines.append(cur)
    return lines


def metrics(font, spacing=2):
    probe = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    one = probe.textbbox((0, 0), "Ag", font=font)
    two = probe.multiline_textbbox((0, 0), "Ag\nAg", font=font, spacing=spacing)
    single = one[3] - one[1]
    return one[1], max(1, (two[3] - two[1]) - single)


def draw_lines(lines, font, fg, bg, margin=2, spacing=2, notch=None):
    img = Image.new("RGB", (WIDTH, HEIGHT), bg)
    draw = ImageDraw.Draw(img)
    top, pitch = metrics(font, spacing)
    count = max(1, -(-(notch[1] - margin) // pitch)) if notch else 0
    y = margin
    for i, line in enumerate(lines):
        x = margin
        draw_text(img, draw, (x, y - top), line, font, fg)
        y += pitch
    return img
