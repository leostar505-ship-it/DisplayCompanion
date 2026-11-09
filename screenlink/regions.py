"""Turn a frame into the smallest set of commands that updates the screen.

The picture is cut into narrow vertical strips. For each strip only the rows that changed are
sent, either as a handful of solid rectangles (cheap for flat bars) or, when the strip is too busy
for that, as a raw image block.
"""
import numpy as np

STRIP = 16
FRAME_OVERHEAD = 6
RECT_BYTES = 6


def _runs_in(a):
    """Rough count of constant-colour horizontal runs in a block."""
    return a.shape[0] + int(np.count_nonzero(a[:, 1:] != a[:, :-1]))


def _rects(a, ox, oy):
    """Exact decomposition of block `a` into solid rectangles (runs merged vertically)."""
    h, w = a.shape
    open_ = {}
    out = []
    for y in range(h):
        row = a[y]
        cuts = (np.flatnonzero(row[1:] != row[:-1]) + 1).tolist()
        starts = [0] + cuts
        ends = cuts + [w]
        cur = {}
        for s, e in zip(starts, ends):
            key = (s, e - s, int(row[s]))
            cur[key] = open_.pop(key, y)
        for (x0, rw, c), y0 in open_.items():
            out.append((x0 + ox, y0 + oy, rw, y - y0, c))
        open_ = cur
    for (x0, rw, c), y0 in open_.items():
        out.append((x0 + ox, y0 + oy, rw, h - y0, c))
    return out


def encode(prev, new):
    """Return (rects, images) that bring a screen showing `prev` to `new`.

    prev is None (or a different shape) for "unknown": everything is sent.
    rects: [(x, y, w, h, rgb565)], images: [(x, y, w, h, bytes)].
    """
    h, w = new.shape
    if prev is None or prev.shape != new.shape:
        changed = np.ones((h, w), dtype=bool)
    else:
        changed = prev != new
    rects = []
    images = []
    for x0 in range(0, w, STRIP):
        x1 = min(w, x0 + STRIP)
        rows = np.flatnonzero(changed[:, x0:x1].any(axis=1))
        if rows.size == 0:
            continue
        y0 = int(rows[0])
        y1 = int(rows[-1]) + 1
        block = new[y0:y1, x0:x1]
        bw, bh = x1 - x0, y1 - y0
        image_cost = FRAME_OVERHEAD + 4 + 2 * bw * bh
        est = _runs_in(block) * RECT_BYTES
        if est < image_cost:
            found = _rects(block, x0, y0)
            if len(found) * RECT_BYTES < image_cost:
                rects += found
                continue
        images.append((x0, y0, bw, bh, np.ascontiguousarray(block, dtype="<u2").tobytes()))
    return rects, images
