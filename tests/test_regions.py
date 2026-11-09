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


def test_lost_frames_are_healed_by_the_rolling_refresh():
    rng = np.random.default_rng(11)
    d = Display()
    lossy = SimBoard()
    lossy.feed(P.clear(0x1234))
    target = scene(rng)
    for i in range(40):
        if i % 4 == 0:
            target = scene(rng)
        d.regions(target)
        data = bytes(d._pending)
        d._pending.clear()
        if i % 3 != 1:
            lossy.feed(data)
    for _ in range(60):
        d.regions(target)
        lossy.feed(bytes(d._pending))
        d._pending.clear()
    assert np.array_equal(lossy.canvas.buf.astype("<u2"), target)


def test_first_frame_is_spread_over_several_calls():
    d = Display()
    lossy = SimBoard()
    lossy.feed(P.clear(0x5555))
    target = scene(np.random.default_rng(2), flat=False)
    sizes = []
    for _ in range(6):
        d.regions(target)
        data = bytes(d._pending)
        sizes.append(len(data))
        d._pending.clear()
        lossy.feed(data)
    assert max(sizes) < 16000
    assert np.array_equal(lossy.canvas.buf.astype("<u2"), target)
