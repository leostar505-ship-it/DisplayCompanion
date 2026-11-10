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
            if probe.textlength(trial, font=font) <= width:
                cur = trial
                continue
            if cur:
                lines.append(cur)
            while probe.textlength(word, font=font) > width and len(word) > 1:
                cut = len(word)
                while cut > 1 and probe.textlength(word[:cut], font=font) > width:
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
        x = margin + (notch[0] if notch and i < count else 0)
        draw.text((x, y - top), line, fill=fg, font=font)
        y += pitch
    return img
