import math

from PIL import Image, ImageDraw

ACCENT = (240, 128, 64)
PETALS = (1.0, 0.3, 0.94, 0.26, 1.0, 0.32, 0.9, 0.28)


def starburst(angle, size, color=ACCENT, fill=0.5):
    ss = 4
    big = size * ss
    img = Image.new("RGBA", (big, big), color + (0,))
    d = ImageDraw.Draw(img)
    c = big / 2.0
    n = len(PETALS)
    for i, length in enumerate(PETALS):
        a = math.radians(angle + i * 360.0 / n)
        r0 = big * 0.07
        r1 = big * (0.2 + 0.22 * length) * (fill / 0.5)
        w = big * 0.052 * (fill / 0.5)
        x0, y0 = c + math.cos(a) * r0, c + math.sin(a) * r0
        x1, y1 = c + math.cos(a) * r1, c + math.sin(a) * r1
        d.line((x0, y0, x1, y1), fill=color, width=int(w * 2))
        for x, y in ((x0, y0), (x1, y1)):
            d.ellipse((x - w, y - w, x + w, y + w), fill=color)
    d.ellipse((c - big * 0.045, c - big * 0.045, c + big * 0.045, c + big * 0.045), fill=color)
    return img.resize((size, size), Image.LANCZOS)
