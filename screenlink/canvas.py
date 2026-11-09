import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .protocol import HEIGHT, WIDTH


def bresenham(x0, y0, x1, y1):
    steep = abs(y1 - y0) > abs(x1 - x0)
    if steep:
        x0, y0 = y0, x0
        x1, y1 = y1, x1
    if x0 > x1:
        x0, x1 = x1, x0
        y0, y1 = y1, y0
    dx = x1 - x0
    dy = abs(y1 - y0)
    err = dx // 2
    ystep = 1 if y0 < y1 else -1
    y = y0
    pts = []
    for x in range(x0, x1 + 1):
        pts.append((y, x) if steep else (x, y))
        err -= dy
        if err < 0:
            y += ystep
            err += dx
    return pts


class Canvas565:
    def __init__(self):
        self.buf = np.zeros((HEIGHT, WIDTH), dtype=np.uint16)
        self._font_cache = {}

    def clear(self, color):
        self.buf[:] = color

    def rects(self, items):
        for x, y, w, h, c in items:
            x2 = min(WIDTH, x + w)
            y2 = min(HEIGHT, y + h)
            if x2 > x and y2 > y:
                self.buf[y:y2, x:x2] = c

    def lines(self, items):
        for x0, y0, x1, y1, c in items:
            for px, py in bresenham(x0, y0, x1, y1):
                if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                    self.buf[py, px] = c

    def pixels(self, items):
        for x, y, c in items:
            if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                self.buf[y, x] = c

    def image(self, x, y, w, h, data):
        if w == 0 or h == 0:
            return
        arr = np.frombuffer(data, dtype="<u2").reshape(h, w)
        x2 = min(WIDTH, x + w)
        y2 = min(HEIGHT, y + h)
        if x2 > x and y2 > y:
            self.buf[y:y2, x:x2] = arr[:y2 - y, :x2 - x]

    def _font(self, size):
        font = self._font_cache.get(size)
        if font is None:
            try:
                font = ImageFont.load_default(size=max(6, 7 * size))
            except TypeError:
                font = ImageFont.load_default()
            self._font_cache[size] = font
        return font

    def text(self, x, y, size, fg, bg, opaque, string):
        size = max(1, size)
        cell_w = 6 * size
        cell_h = 8 * size
        if opaque:
            self.rects([(x, y, min(255, cell_w * len(string)), cell_h, bg)])
        mask = Image.new("L", (cell_w * len(string) + 2, cell_h + 2), 0)
        ImageDraw.Draw(mask).text((0, 0), string, fill=255, font=self._font(size))
        m = np.array(mask) > 100
        ys, xs = np.nonzero(m)
        for yy, xx in zip(ys, xs):
            px = x + int(xx)
            py = y + int(yy)
            if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                self.buf[py, px] = fg

    def to_rgb(self):
        a = self.buf
        r = ((a >> 11) & 31).astype(np.uint8)
        g = ((a >> 5) & 63).astype(np.uint8)
        b = (a & 31).astype(np.uint8)
        out = np.empty((HEIGHT, WIDTH, 3), dtype=np.uint8)
        out[..., 0] = (r << 3) | (r >> 2)
        out[..., 1] = (g << 2) | (g >> 4)
        out[..., 2] = (b << 3) | (b >> 2)
        return out

    def to_image(self):
        return Image.fromarray(self.to_rgb(), "RGB")

    def snapshot(self):
        return self.buf.copy()

    def restore(self, snap):
        self.buf[:] = snap
