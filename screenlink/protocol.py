import struct

WIDTH = 160
HEIGHT = 80
MAGIC = b"\xa5\x5a"
MAX_PAYLOAD = 26112
BAUD = 921600

CMD_HELLO = 0x01
CMD_CLEAR = 0x02
CMD_RECTS = 0x03
CMD_LINES = 0x04
CMD_PIXELS = 0x05
CMD_IMAGE = 0x06
CMD_TEXT = 0x07
CMD_FLIP = 0x08
CMD_INVERT = 0x09
CMD_SWAP_RB = 0x0A
CMD_PRESENT = 0x0C

COMMAND_NAMES = {
    "HELLO": CMD_HELLO,
    "CLEAR": CMD_CLEAR,
    "RECTS": CMD_RECTS,
    "LINES": CMD_LINES,
    "PIXELS": CMD_PIXELS,
    "IMAGE": CMD_IMAGE,
    "TEXT": CMD_TEXT,
    "FLIP": CMD_FLIP,
    "INVERT": CMD_INVERT,
    "SWAP_RB": CMD_SWAP_RB,
    "PRESENT": CMD_PRESENT,
}

HELLO_REPLY_PREFIX = "SCREENLINK"


def rgb565(r, g, b):
    return ((int(r) & 0xF8) << 8) | ((int(g) & 0xFC) << 3) | (int(b) >> 3)


def rgb565_to_rgb(v):
    r = (v >> 11) & 31
    g = (v >> 5) & 63
    b = v & 31
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))


def checksum(cmd, payload):
    n = len(payload)
    return (cmd + (n & 0xFF) + (n >> 8) + sum(payload)) & 0xFF


def frame(cmd, payload=b""):
    payload = bytes(payload)
    n = len(payload)
    if n > MAX_PAYLOAD:
        raise ValueError("payload too large")
    return MAGIC + bytes((cmd, n & 0xFF, n >> 8)) + payload + bytes((checksum(cmd, payload),))


def _chunks(items, size):
    items = list(items)
    for i in range(0, len(items), size):
        yield items[i:i + size]


def hello():
    return frame(CMD_HELLO)


def clear(color):
    return frame(CMD_CLEAR, struct.pack("<H", color))


def rects(items):
    out = bytearray()
    for chunk in _chunks(items, 255):
        body = bytearray((len(chunk),))
        for x, y, w, h, c in chunk:
            body += struct.pack("<BBBBH", x, y, w, h, c)
        out += frame(CMD_RECTS, body)
    return bytes(out)


def lines(items):
    out = bytearray()
    for chunk in _chunks(items, 255):
        body = bytearray((len(chunk),))
        for x0, y0, x1, y1, c in chunk:
            body += struct.pack("<BBBBH", x0, y0, x1, y1, c)
        out += frame(CMD_LINES, body)
    return bytes(out)


def pixels(items):
    out = bytearray()
    for chunk in _chunks(items, 6000):
        body = bytearray(struct.pack("<H", len(chunk)))
        for x, y, c in chunk:
            body += struct.pack("<BBH", x, y, c)
        out += frame(CMD_PIXELS, body)
    return bytes(out)


def image(x, y, w, h, data):
    if len(data) != w * h * 2:
        raise ValueError("image data size mismatch")
    return frame(CMD_IMAGE, bytes((x, y, w, h)) + bytes(data))


def text(x, y, size, fg, bg, opaque, string):
    raw = string.encode("ascii", "replace")[:255]
    head = struct.pack("<BBBHHBB", x, y, size, fg, bg, 1 if opaque else 0, len(raw))
    return frame(CMD_TEXT, head + raw)


def rotate(quarters):
    return frame(CMD_FLIP, bytes((int(quarters) & 3,)))


def flip(on):
    return rotate(2 if on else 0)


def invert(on):
    return frame(CMD_INVERT, bytes((1 if on else 0,)))


def swap_rb(on):
    return frame(CMD_SWAP_RB, bytes((1 if on else 0,)))


def present():
    return frame(CMD_PRESENT)


class Decoder:
    def __init__(self):
        self.buf = bytearray()
        self.bad_checksums = 0

    def feed(self, data):
        self.buf += data
        out = []
        while True:
            i = self.buf.find(MAGIC)
            if i < 0:
                keep = 1 if self.buf.endswith(MAGIC[:1]) else 0
                del self.buf[:len(self.buf) - keep]
                break
            if i > 0:
                del self.buf[:i]
            if len(self.buf) < 5:
                break
            cmd = self.buf[2]
            n = self.buf[3] | (self.buf[4] << 8)
            if n > MAX_PAYLOAD:
                del self.buf[:5]
                continue
            total = 5 + n + 1
            if len(self.buf) < total:
                break
            payload = bytes(self.buf[5:5 + n])
            chk = self.buf[5 + n]
            del self.buf[:total]
            if chk == checksum(cmd, payload):
                out.append((cmd, payload))
            else:
                self.bad_checksums += 1
        return out
