import struct

from . import protocol as P
from .canvas import Canvas565


class SimBoard:
    def __init__(self):
        self.canvas = Canvas565()
        self.decoder = P.Decoder()
        self.presented = self.canvas.snapshot()
        self.dirty = False
        self.rotation = 0
        self.invert = False
        self.swap_rb = False
        self.replies = bytearray()
        self.frames = 0
        self.present_count = 0

    @property
    def buf(self):
        return self.canvas.buf

    def feed(self, data):
        for cmd, payload in self.decoder.feed(data):
            self.handle(cmd, payload)

    def flush(self):
        if self.dirty:
            self.present()

    def present(self):
        self.presented = self.canvas.snapshot()
        self.dirty = False
        self.present_count += 1

    def take_replies(self):
        out = bytes(self.replies)
        self.replies.clear()
        return out

    def handle(self, cmd, p):
        self.frames += 1
        c = self.canvas
        if cmd == P.CMD_HELLO:
            self.replies += f"{P.HELLO_REPLY_PREFIX} 1 {P.WIDTH}x{P.HEIGHT}\n".encode()
        elif cmd == P.CMD_CLEAR:
            if len(p) >= 2:
                c.clear(struct.unpack_from("<H", p)[0])
                self.dirty = True
        elif cmd == P.CMD_RECTS:
            items = self._records(p, 1, 6, "<BBBBH")
            if items is not None:
                c.rects(items)
                self.dirty = True
        elif cmd == P.CMD_LINES:
            items = self._records(p, 1, 6, "<BBBBH")
            if items is not None:
                c.lines(items)
                self.dirty = True
        elif cmd == P.CMD_PIXELS:
            if len(p) >= 2:
                n = struct.unpack_from("<H", p)[0]
                if 2 + n * 4 <= len(p):
                    c.pixels([struct.unpack_from("<BBH", p, 2 + i * 4) for i in range(n)])
                    self.dirty = True
        elif cmd == P.CMD_IMAGE:
            if len(p) >= 4:
                x, y, w, h = p[0], p[1], p[2], p[3]
                if len(p) == 4 + w * h * 2:
                    c.image(x, y, w, h, p[4:])
                    self.dirty = True
        elif cmd == P.CMD_TEXT:
            if len(p) >= 9:
                x, y, size, fg, bg, flags, n = struct.unpack_from("<BBBHHBB", p)
                if 9 + n <= len(p):
                    c.text(x, y, size, fg, bg, bool(flags & 1), p[9:9 + n].decode("ascii", "replace"))
                    self.dirty = True
        elif cmd == P.CMD_FLIP:
            self.rotation = (p[0] & 3) if p else self.rotation
        elif cmd == P.CMD_INVERT:
            self.invert = bool(p[0]) if p else self.invert
        elif cmd == P.CMD_SWAP_RB:
            self.swap_rb = bool(p[0]) if p else self.swap_rb
        elif cmd == P.CMD_PRESENT:
            self.present()

    @staticmethod
    def _records(p, head, size, fmt):
        if len(p) < head:
            return None
        n = p[0]
        if head + n * size > len(p):
            return None
        return [struct.unpack_from(fmt, p, head + i * size) for i in range(n)]
