import numpy as np

from screenlink import colors, protocol as P
from screenlink.analysis import Analyser
from screenlink.canvas import bresenham
from screenlink.display import Display
from screenlink.link import SimLink
from screenlink.peaks import PeakHold
from screenlink.simboard import SimBoard


def test_rgb565_roundtrip():
    for rgb in [(0, 0, 0), (255, 255, 255), (255, 0, 0), (0, 255, 0), (0, 0, 255)]:
        assert P.rgb565_to_rgb(P.rgb565(*rgb)) == rgb


def test_frame_and_decoder_roundtrip():
    data = P.clear(0x1234) + P.rects([(1, 2, 3, 4, 0xF800)]) + P.present()
    dec = P.Decoder()
    out = dec.feed(data)
    assert [c for c, _ in out] == [P.CMD_CLEAR, P.CMD_RECTS, P.CMD_PRESENT]


def test_decoder_split_chunks_and_garbage():
    data = b"\x00\x11\xa5" + P.clear(5) + b"junk" + P.rects([(0, 0, 2, 2, 7)])
    dec = P.Decoder()
    got = []
    for i in range(0, len(data), 3):
        got += dec.feed(data[i:i + 3])
    assert [c for c, _ in got] == [P.CMD_CLEAR, P.CMD_RECTS]


def test_bad_checksum_is_dropped_whole():
    good = P.clear(9)
    bad = bytearray(P.rects([(0, 0, 4, 4, 1)]))
    bad[-1] ^= 0xFF
    dec = P.Decoder()
    out = dec.feed(bytes(bad) + good)
    assert [c for c, _ in out] == [P.CMD_CLEAR]
    assert dec.bad_checksums == 1


def test_rects_chunk_over_255():
    items = [(i % 150, 0, 1, 1, 3) for i in range(600)]
    dec = P.Decoder()
    out = dec.feed(P.rects(items))
    assert len(out) == 3
    assert out[0][1][0] == 255


def test_simboard_primitives():
    b = SimBoard()
    b.feed(P.clear(0) + P.rects([(10, 10, 5, 5, 0xFFFF)]) + P.lines([(0, 0, 159, 79, 0xF800)])
           + P.pixels([(100, 40, 0x07E0)]) + P.present())
    assert b.presented[12, 12] == 0xFFFF
    assert b.presented[0, 0] == 0xF800
    assert b.presented[79, 159] == 0xF800
    assert b.presented[40, 100] == 0x07E0


def test_image_clipped_at_edges():
    b = SimBoard()
    data = np.full((10, 20), 0xABCD, dtype="<u2").tobytes()
    b.feed(P.image(150, 75, 20 if 150 + 20 <= 255 else 20, 10, data) + P.present())
    assert b.presented[75, 150] == 0xABCD
    assert b.presented[79, 159] == 0xABCD


def test_hello_reply():
    b = SimBoard()
    b.feed(P.hello())
    assert b.take_replies().decode().startswith("SCREENLINK 1 160x120")


def test_display_sends_and_mirrors_locally():
    link = SimLink()
    link.open()
    d = Display()
    d.set_link(link)
    d.clear((0, 0, 0))
    d.rects([(0, 0, 10, 10, (255, 0, 0))])
    d.flush()
    assert (d.canvas.buf == link.board.canvas.buf).all()
    assert link.board.presented[5, 5] == P.rgb565(255, 0, 0)


def test_silent_updates_local_only():
    link = SimLink()
    link.open()
    d = Display()
    d.set_link(link)
    with d.silent():
        d.rects([(0, 0, 10, 10, (0, 255, 0))])
    d.flush()
    assert d.canvas.buf[5, 5] == P.rgb565(0, 255, 0)
    assert link.board.canvas.buf[5, 5] == 0


def test_bresenham_endpoints():
    pts = bresenham(3, 7, 90, 12)
    assert pts[0] == (3, 7) and pts[-1] == (90, 12)
    assert bresenham(5, 5, 5, 9) == [(5, 5), (5, 6), (5, 7), (5, 8), (5, 9)]


def test_peak_hold_holds_then_falls():
    p = PeakHold(1, hold_seconds=1.0, fall_per_second=0.5)
    p.update([0.8], 0.016)
    for _ in range(50):
        p.update([0.1], 0.016)
    assert abs(p.peaks[0] - 0.8) < 1e-9
    for _ in range(120):
        p.update([0.1], 0.016)
    assert p.peaks[0] < 0.8
    assert p.peaks[0] >= 0.1


def test_peak_hold_pushed_up_and_infinite_and_reset():
    p = PeakHold(2, hold_seconds=0.2, fall_per_second=1.0, infinite=True)
    p.update([0.5, 0.2], 0.016)
    for _ in range(300):
        p.update([0.0, 0.3], 0.016)
    assert abs(p.peaks[0] - 0.5) < 1e-9
    assert abs(p.peaks[1] - 0.3) < 1e-9
    p.reset()
    assert p.peaks.max() == 0.0


def test_analyser_finds_tone_band():
    rate = 48000
    a = Analyser(rate, bands=32)
    t = np.arange(4096) / rate
    sig = 0.5 * np.sin(2 * np.pi * 1000 * t)
    for _ in range(40):
        lv = a.process(sig, 0.016)
    peak_band = int(np.argmax(lv))
    lo, hi = a.freqs[a.lo[peak_band]], a.freqs[a.hi[peak_band]]
    assert lo - 100 <= 1000 <= hi + 100


def test_analyser_silence_is_flat():
    a = Analyser(48000)
    lv = a.process(np.zeros(2048), 0.016)
    assert lv.max() < 0.05


def test_rainbow_ends_and_hex():
    assert colors.rainbow_rgb(0.0) == (255, 0, 0)
    r, g, b = colors.rainbow_rgb(1.0)
    assert r > 200 and b > 100 and g < 60
    assert colors.parse_hex("#ff8800") == (255, 136, 0)
    assert colors.parse_hex("f80") == (255, 136, 0)
    assert colors.parse_hex("nope") is None
    assert colors.loudness_rgb(1.0) == (255, 0, 0)


def test_old_visualiser_port_renders_pixels_on_the_screen_size():
    import time
    import numpy as np
    from screenlink.audiovis.analysis import Analyser
    from screenlink.audiovis.capture import DemoSource
    from screenlink.audiovis.raster import Raster
    from screenlink.audiovis.visuals import VISUALS, Look
    from screenlink.display import H, W

    src = DemoSource()
    an = Analyser(src.rate)
    look = Look("rainbow", (255, 0, 0), 1.6, 1.6, 0.5)
    for name, cls in VISUALS.items():
        vis = cls()
        raster = Raster(W, H, False)
        for _ in range(20):
            an.update(src.latest(), 0.033, time.perf_counter())
            px = raster.render(vis.frame(W, H, 0.033, an, look, True))
        assert px.shape == (H, W, 3)
        assert int(np.count_nonzero(px)) > 50, name


def test_bars_hold_time_keeps_peaks_up():
    import numpy as np
    from screenlink.audiovis.analysis import BANDS, Analyser
    from screenlink.audiovis.visuals import BarsVisual, Look

    an = Analyser()
    look = Look("rainbow", (255, 0, 0), 1.6)
    look.hold = 5.0
    vis = BarsVisual()
    an.vals = np.ones(BANDS)
    vis.frame(160, 120, 0.03, an, look, True)
    top = vis.peaks[0]
    an.vals = np.zeros(BANDS)
    for _ in range(30):
        vis.frame(160, 120, 0.03, an, look, True)
    assert vis.peaks[0] == top
    look.hold = 0.0
    for _ in range(30):
        vis.frame(160, 120, 0.03, an, look, True)
    assert vis.peaks[0] < top


def test_bar_smoothness_slows_the_fall_between_loud_and_quiet():
    import numpy as np
    from screenlink.modes.visualiser import VisualiserMode

    class Stub:
        def get(self_inner):
            return self_inner.v

    mode = VisualiserMode.__new__(VisualiserMode)
    from screenlink.audiovis.analysis import Analyser

    mode.analyser = Analyser()
    mode.shown = None
    mode.bar_smooth = Stub()
    mode.bar_smooth.v = 0.0
    mode.analyser.vals = np.ones(32)
    mode._smooth_bars(0.05)
    mode.analyser.vals = np.zeros(32)
    mode._smooth_bars(0.05)
    assert mode.analyser.vals.max() == 0.0
    mode.bar_smooth.v = 0.8
    mode.analyser.vals = np.ones(32)
    for _ in range(10):
        mode._smooth_bars(0.05)
    mode.analyser.vals = np.zeros(32)
    mode._smooth_bars(0.05)
    assert 0.5 < mode.analyser.vals.max() < 1.0


def frame_sizes(raw):
    sizes = []
    i = 0
    while i < len(raw):
        assert raw[i:i + 2] == bytes((0xA5, 0x5A))
        n = raw[i + 3] | (raw[i + 4] << 8)
        sizes.append(n)
        i += 5 + n + 1
    return sizes


def test_images_are_split_into_small_commands():
    from PIL import Image
    import numpy as np
    from screenlink.display import Display
    rng = np.random.default_rng(4)
    img = Image.fromarray(rng.integers(0, 256, (120, 160, 3), dtype=np.uint8), "RGB")
    d = Display()
    d.image(0, 0, img)
    sizes = frame_sizes(bytes(d._pending))
    assert len(sizes) >= 6
    assert max(sizes) < 6500
    d2 = Display()
    d2.send_full()
    assert max(frame_sizes(bytes(d2._pending))) < 6500
