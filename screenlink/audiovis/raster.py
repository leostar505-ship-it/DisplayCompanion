import math

import numpy as np

from . import colors

MONO_ALPHA_CUTOFF = 0.35
WHITE = (255, 255, 255)


class Raster:
    def __init__(self, width, height, mono=False):
        self.w = int(width)
        self.h = int(height)
        self.mono = mono
        self.px = np.zeros((self.h, self.w, 3), dtype=np.uint8)
        ys, xs = np.mgrid[0 : self.h, 0 : self.w]
        self.xs = xs.astype(np.float32) + 0.5
        self.ys = ys.astype(np.float32) + 0.5

    def clear(self):
        self.px[:] = 0

    def rect(self, x0, y0, x1, y1, rgb):
        ix0 = int(round(x0))
        iy0 = int(round(y0))
        ix1 = int(round(x1))
        iy1 = int(round(y1))
        if ix1 <= ix0:
            ix1 = ix0 + 1
        if iy1 <= iy0:
            iy1 = iy0 + 1
        ix0 = max(0, ix0)
        iy0 = max(0, iy0)
        ix1 = min(self.w, ix1)
        iy1 = min(self.h, iy1)
        if ix1 > ix0 and iy1 > iy0:
            self.px[iy0:iy1, ix0:ix1] = rgb

    def line(self, x0, y0, x1, y1, width, rgb):
        dx = x1 - x0
        dy = y1 - y0
        length = math.hypot(dx, dy)
        if length < 1e-6:
            ux, uy = 1.0, 0.0
        else:
            ux, uy = dx / length, dy / length
        half = max(width, 1.0) / 2.0
        pad = half + 1.0
        bx0 = max(0, int(math.floor(min(x0, x1) - pad)))
        bx1 = min(self.w, int(math.ceil(max(x0, x1) + pad)))
        by0 = max(0, int(math.floor(min(y0, y1) - pad)))
        by1 = min(self.h, int(math.ceil(max(y0, y1) + pad)))
        if bx1 <= bx0 or by1 <= by0:
            return
        rx = self.xs[by0:by1, bx0:bx1] - x0
        ry = self.ys[by0:by1, bx0:bx1] - y0
        along = rx * ux + ry * uy
        across = rx * uy - ry * ux
        mask = (along >= -0.5) & (along <= length + 0.5) & (across > -half) & (across <= half)
        view = self.px[by0:by1, bx0:bx1]
        view[mask] = rgb

    def ring(self, cx, cy, radius, width, rgb):
        half = max(width, 1.0) / 2.0
        ext = radius + half + 1.0
        bx0 = max(0, int(math.floor(cx - ext)))
        bx1 = min(self.w, int(math.ceil(cx + ext)))
        by0 = max(0, int(math.floor(cy - ext)))
        by1 = min(self.h, int(math.ceil(cy + ext)))
        if bx1 <= bx0 or by1 <= by0:
            return
        dist = np.hypot(self.xs[by0:by1, bx0:bx1] - cx, self.ys[by0:by1, bx0:bx1] - cy)
        mask = np.abs(dist - radius) <= half
        view = self.px[by0:by1, bx0:bx1]
        view[mask] = rgb

    def render(self, prims):
        self.clear()
        for p in prims:
            if self.mono:
                if p.alpha < MONO_ALPHA_CUTOFF:
                    continue
                rgb = WHITE
            else:
                rgb = colors.blend(p.rgb, p.alpha) if p.alpha < 1.0 else p.rgb
            if p.kind == "line":
                self.line(p.a, p.b, p.c, p.d, p.w, rgb)
            elif p.kind == "rect":
                self.rect(p.a, p.b, p.c, p.d, rgb)
            else:
                self.ring(p.a, p.b, p.c, p.w, rgb)
        return self.px

    def ppm(self):
        return b"P6\n%d %d\n255\n" % (self.w, self.h) + self.px.tobytes()
