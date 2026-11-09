import contextlib
import time

import numpy as np
from PIL import Image

from . import protocol as P
from .simboard import SimBoard

W = P.WIDTH
H = P.HEIGHT


def to565(rgb):
    return P.rgb565(rgb[0], rgb[1], rgb[2])


def clip_rect(x, y, w, h):
    x = int(x)
    y = int(y)
    x2 = min(W, x + int(w))
    y2 = min(H, y + int(h))
    x = max(0, x)
    y = max(0, y)
    if x2 <= x or y2 <= y:
        return None
    return (x, y, x2 - x, y2 - y)


def image_to_565(img):
    arr = np.asarray(img.convert("RGB"), dtype=np.uint16)
    out = ((arr[..., 0] & 0xF8) << 8) | ((arr[..., 1] & 0xFC) << 3) | (arr[..., 2] >> 3)
    return out.astype("<u2")


class Display:
    def __init__(self):
        self.board = SimBoard()
        self.link = None
        self.silent_depth = 0
        self._pending = bytearray()
        self.version = 0
        self.inflight = None
        self.timed_out = False

    @property
    def canvas(self):
        return self.board.canvas

    def set_link(self, link):
        self.link = link

    @contextlib.contextmanager
    def silent(self):
        self.silent_depth += 1
        try:
            yield
        finally:
            self.silent_depth -= 1

    def _add(self, data):
        self.board.feed(data)
        self.version += 1
        if self.silent_depth == 0:
            self._pending += data

    def _wire_only(self, data):
        if self.link is not None and self.link.is_open:
            self.link.send(data)

    def ready(self):
        if self.inflight is None:
            return True
        if time.perf_counter() - self.inflight > 0.4:
            self.inflight = None
            self.timed_out = True
            return True
        return False

    def ack(self):
        self.inflight = None

    def take_timeout(self):
        t = self.timed_out
        self.timed_out = False
        return t

    def flush(self, realtime=False, acked=False):
        if not self._pending:
            return
        data = bytes(self._pending) + P.present()
        self._pending.clear()
        if self.link is not None and self.link.is_open:
            if acked:
                self.inflight = time.perf_counter()
                self.link.send(data)
            elif realtime:
                self.link.send_latest(data)
            else:
                self.link.send(data)

    def clear(self, rgb):
        self._add(P.clear(to565(rgb)))

    def rects(self, items):
        out = []
        for x, y, w, h, rgb in items:
            r = clip_rect(x, y, w, h)
            if r is not None:
                out.append(r + (to565(rgb),))
        if out:
            self._add(P.rects(out))

    def lines(self, items):
        out = []
        for x0, y0, x1, y1, rgb in items:
            out.append((
                min(W - 1, max(0, int(x0))),
                min(H - 1, max(0, int(y0))),
                min(W - 1, max(0, int(x1))),
                min(H - 1, max(0, int(y1))),
                to565(rgb),
            ))
        if out:
            self._add(P.lines(out))

    def pixels(self, items):
        out = []
        for x, y, rgb in items:
            if 0 <= x < W and 0 <= y < H:
                out.append((int(x), int(y), to565(rgb)))
        if out:
            self._add(P.pixels(out))

    def image(self, x, y, img):
        img = img.convert("RGB")
        w, h = img.size
        if x < 0 or y < 0:
            img = img.crop((max(0, -x), max(0, -y), w, h))
            x = max(0, x)
            y = max(0, y)
            w, h = img.size
        w = min(w, W - x)
        h = min(h, H - y)
        if w <= 0 or h <= 0:
            return
        img = img.crop((0, 0, w, h))
        self._add(P.image(x, y, w, h, image_to_565(img).tobytes()))

    def full_image(self, img):
        self.image(0, 0, img)

    def send_full(self):
        data = np.ascontiguousarray(self.canvas.buf.astype("<u2")).tobytes()
        self._add(P.image(0, 0, W, H, data))

    def text(self, x, y, size, rgb, bg_rgb, opaque, string):
        self._add(P.text(int(x), int(y), int(size), to565(rgb), to565(bg_rgb), opaque, string))

    def set_flip(self, on):
        self._wire_only(P.flip(on))

    def set_rotation(self, quarters):
        self._wire_only(P.rotate(quarters))

    def set_invert(self, on):
        self._wire_only(P.invert(on))

    def set_swap_rb(self, on):
        self._wire_only(P.swap_rb(on))

    def hello(self):
        self._wire_only(P.hello())

    def raw(self, data):
        self.board.feed(data)
        self.version += 1
        if self.link is not None and self.link.is_open:
            self.link.send(bytes(data))

    def restore(self, snapshot):
        self.canvas.restore(snapshot)
        self.version += 1

    def snapshot(self):
        return self.canvas.snapshot()

    def rgb_image(self):
        return Image.fromarray(self.canvas.to_rgb(), "RGB")
