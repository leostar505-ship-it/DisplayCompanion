import numpy as np

from screenlink import protocol as P
from screenlink.display import Display
from screenlink.regions import encode
from screenlink.simboard import SimBoard


def apply(board, rects, images):
    if rects:
        board.feed(P.rects(rects))
    for x, y, w, h, data in images:
        board.feed(P.image(x, y, w, h, data))


def scene(rng, flat=True):
    a = np.zeros((P.HEIGHT, P.WIDTH), dtype="<u2")
    for _ in range(12):
        x, y = rng.integers(0, 150), rng.integers(0, 100)
        w, h = rng.integers(1, 40), rng.integers(1, 60)
        a[y:y + h, x:x + w] = rng.integers(0, 65536)
    if not flat:
        a ^= rng.integers(0, 4, a.shape).astype("<u2")
    return a


def test_regions_reproduce_frame_exactly():
    rng = np.random.default_rng(3)
    board = SimBoard()
    prev = None
    for i in range(12):
        new = scene(rng, flat=(i % 3 != 2))
        rects, images = encode(prev, new)
        apply(board, rects, images)
        assert np.array_equal(board.canvas.buf.astype("<u2"), new)
        prev = new


def test_flat_bars_use_rects_and_are_small():
    prev = np.zeros((P.HEIGHT, P.WIDTH), dtype="<u2")
    new = prev.copy()
    new[60:120, 10:18] = 0xF800
    new[30:120, 40:48] = 0x07E0
    rects, images = encode(prev, new)
    assert rects and not images
    assert sum(len(P.rects([r])) for r in rects) < 100


def test_unchanged_frame_sends_nothing():
    a = scene(np.random.default_rng(1))
    assert encode(a, a.copy()) == ([], [])


def test_noisy_strip_falls_back_to_image():
    rng = np.random.default_rng(5)
    prev = np.zeros((P.HEIGHT, P.WIDTH), dtype="<u2")
    new = rng.integers(0, 65536, prev.shape).astype("<u2")
    rects, images = encode(prev, new)
    assert images and not rects


def test_ack_window_allows_two_frames_in_flight():
    d = Display()
    assert d.ready()
    d.inflight.append(0.0)
    d.inflight[0] = __import__("time").perf_counter()
    assert d.ready()
    d.inflight.append(__import__("time").perf_counter())
    assert not d.ready()
    d.ack()
    assert d.ready()
