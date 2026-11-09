import pathlib
import random
import shutil
import subprocess

import numpy as np
import pytest

from screenlink import protocol as P
from screenlink.simboard import SimBoard

ROOT = pathlib.Path(__file__).resolve().parent
SKETCH = ROOT.parent / "firmware" / "ScreenLink" / "ScreenLink.ino"


@pytest.fixture(scope="module")
def sim(tmp_path_factory):
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")
    out = tmp_path_factory.mktemp("fw2") / "fw_sim2"
    cmd = [
        "g++", "-std=c++17", "-O1", "-DPANEL_VARIANT=2", "-DSCREEN_H=120", f"-I{ROOT / 'stubs'}",
        "-x", "c++", str(SKETCH), "-x", "c++", str(ROOT / "stubs" / "harness2.cpp"), "-o", str(out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return out


def run(sim, tmp_path, data, chunk=97):
    inp = tmp_path / "in.bin"
    outp = tmp_path / "out.bin"
    inp.write_bytes(data)
    res = subprocess.run([str(sim), str(inp), str(outp), str(chunk)], capture_output=True)
    assert res.returncode == 0, res.stderr
    raw = outp.read_bytes()
    lw, lh = np.frombuffer(raw[:8], dtype="<i4")
    fb = np.frombuffer(raw[8:], dtype="<u2").reshape(lh, lw)
    return fb, res.stdout.decode("ascii", "replace")


def swap_rb(arr):
    a = arr.astype(np.uint32)
    return (((a & 0x1F) << 11) | (a & 0x07E0) | (a >> 11)).astype(np.uint16)


def expected(board):
    img = np.asarray(board.presented, dtype="<u2")
    if board.swap_rb:
        img = swap_rb(img)
    q = board.rotation
    if q & 1:
        out = np.zeros((320, 240), dtype="<u2")
        for r in range(320):
            x = r // 2 if q == 1 else P.WIDTH - 1 - r // 2
            for c in range(240):
                i = c // 2
                y = P.HEIGHT - 1 - i if q == 1 else i
                out[r, c] = img[y, x]
        return out
    return np.repeat(np.repeat(img, 2, axis=0), 2, axis=1)


def stream(rng, frames=25, with_rotation=False):
    out = bytearray(P.clear(rng.randrange(65536)) + P.present())
    for _ in range(frames):
        kind = rng.choice(["rects", "lines", "pixels", "image"])
        if kind == "rects":
            out += P.rects([(rng.randrange(0, 150), rng.randrange(0, 110), rng.randrange(1, 30),
                             rng.randrange(1, 25), rng.randrange(65536)) for _ in range(rng.randrange(1, 6))])
        elif kind == "lines":
            out += P.lines([(rng.randrange(0, 160), rng.randrange(0, 120), rng.randrange(0, 160),
                             rng.randrange(0, 120), rng.randrange(65536))])
        elif kind == "pixels":
            out += P.pixels([(rng.randrange(0, 160), rng.randrange(0, 120), rng.randrange(65536))
                             for _ in range(rng.randrange(1, 20))])
        elif kind == "text":
            out += P.text(rng.randrange(0, 120), rng.randrange(0, 100), rng.randrange(1, 3), rng.randrange(65536),
                          rng.randrange(65536), rng.random() < 0.5, "Hi!")
        else:
            w, h = rng.randrange(1, 30), rng.randrange(1, 20)
            x, y = rng.randrange(0, 160 - w), rng.randrange(0, 120 - h)
            data = bytes(rng.randrange(256) for _ in range(w * h * 2))
            out += P.image(x, y, w, h, data)
        if with_rotation and rng.random() < 0.15:
            out += P.rotate(rng.randrange(4))
        if with_rotation and rng.random() < 0.1:
            out += P.swap_rb(rng.random() < 0.5)
        if rng.random() < 0.7:
            out += P.present()
    out += P.present()
    return bytes(out)


@pytest.mark.parametrize("seed", range(6))
def test_partial_redraw_matches_full_frame(sim, tmp_path, seed):
    data = stream(random.Random(seed))
    board = SimBoard()
    board.feed(data)
    board.flush()
    fb, out = run(sim, tmp_path, data)
    assert np.array_equal(fb, expected(board))
    assert out.count("K\n") == data.count(P.present())


@pytest.mark.parametrize("seed", range(6))
def test_partial_redraw_with_rotation_and_swap(sim, tmp_path, seed):
    data = stream(random.Random(100 + seed), with_rotation=True)
    board = SimBoard()
    board.feed(data)
    board.flush()
    fb, _ = run(sim, tmp_path, data)
    assert np.array_equal(fb, expected(board))
