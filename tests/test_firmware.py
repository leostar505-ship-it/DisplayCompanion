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
    out = tmp_path_factory.mktemp("fw") / "fw_sim"
    cmd = [
        "g++", "-std=c++17", "-O1", "-DPANEL_VARIANT=0", "-DSCREEN_H=120", f"-I{ROOT / 'stubs'}",
        "-x", "c++", str(SKETCH), "-x", "c++", str(ROOT / "stubs" / "harness.cpp"),
        "-o", str(out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return out


def run_fw(sim, tmp_path, data, chunk=64):
    inp = tmp_path / "in.bin"
    outp = tmp_path / "out.bin"
    inp.write_bytes(data)
    res = subprocess.run([str(sim), str(inp), str(outp), str(chunk)], capture_output=True)
    assert res.returncode == 0, res.stderr
    frame = np.frombuffer(outp.read_bytes(), dtype="<u2").reshape(P.HEIGHT, P.WIDTH)
    return frame, res.stdout.decode("ascii", "replace"), res.stderr.decode()


def expected(data):
    b = SimBoard()
    b.feed(data)
    b.flush()
    return b.presented.copy(), b


def swap_rb(arr):
    a = arr.astype(np.uint32)
    return (((a & 0x1F) << 11) | (a & 0x07E0) | (a >> 11)).astype(np.uint16)


def random_stream(rng, parts=40):
    out = bytearray(P.clear(rng.randrange(65536)))
    for _ in range(parts):
        kind = rng.choice(["rects", "lines", "pixels", "image"])
        if kind == "rects":
            out += P.rects([(rng.randrange(0, 170), rng.randrange(0, 90), rng.randrange(0, 60),
                             rng.randrange(0, 40), rng.randrange(65536)) for _ in range(rng.randrange(1, 30))])
        elif kind == "lines":
            out += P.lines([(rng.randrange(0, 170), rng.randrange(0, 90), rng.randrange(0, 170),
                             rng.randrange(0, 90), rng.randrange(65536)) for _ in range(rng.randrange(1, 20))])
        elif kind == "pixels":
            out += P.pixels([(rng.randrange(0, 170), rng.randrange(0, 90), rng.randrange(65536))
                             for _ in range(rng.randrange(1, 200))])
        else:
            w = rng.randrange(1, 100)
            h = rng.randrange(1, 60)
            x = rng.randrange(0, 160)
            y = rng.randrange(0, 80)
            data = np.array([rng.randrange(65536) for _ in range(w * h)], dtype="<u2").tobytes()
            out += P.image(x, y, w, h, data)
        if rng.random() < 0.2:
            out += bytes(rng.randrange(256) for _ in range(rng.randrange(1, 12)))
    out += P.present()
    return bytes(out)


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("chunk", [1, 7, 64, 4096])
def test_random_streams_match_python_reference(sim, tmp_path, seed, chunk):
    data = random_stream(random.Random(seed))
    got, _, _ = run_fw(sim, tmp_path, data, chunk)
    want, _ = expected(data)
    assert (got == want).all()


def test_full_frame_image(sim, tmp_path):
    arr = np.random.RandomState(7).randint(0, 65536, size=(P.HEIGHT, P.WIDTH)).astype("<u2")
    data = P.clear(0) + P.image(0, 0, P.WIDTH, P.HEIGHT, arr.tobytes()) + P.present()
    got, _, _ = run_fw(sim, tmp_path, data, 64)
    assert (got == arr).all()


def test_bad_checksum_frame_ignored_and_error_reported(sim, tmp_path):
    bad = bytearray(P.rects([(0, 0, 160, 80, 0xFFFF)]))
    bad[-1] ^= 0x55
    data = P.clear(0x001F) + bytes(bad) + P.rects([(0, 0, 4, 4, 0xF800)]) + P.present()
    got, text, _ = run_fw(sim, tmp_path, data, 32)
    assert got[0, 0] == 0xF800
    assert got[40, 80] == 0x001F
    assert "ERR chk" in text


def test_hello_reply(sim, tmp_path):
    _, text, _ = run_fw(sim, tmp_path, P.hello(), 16)
    assert text.startswith("SCREENLINK 1 160x120")


def test_swap_rb_applied_at_present(sim, tmp_path):
    data = P.swap_rb(True) + P.clear(0xF800) + P.rects([(0, 0, 10, 10, 0x001F)]) + P.present()
    got, _, _ = run_fw(sim, tmp_path, data, 64)
    assert got[50, 50] == 0x001F
    assert got[5, 5] == 0xF800


def test_flip_and_invert_reach_panel(sim, tmp_path):
    data = P.flip(True) + P.invert(True) + P.clear(1) + P.present()
    _, _, err = run_fw(sim, tmp_path, data, 64)
    assert "rotation=3" in err
    assert "inverted=1" in err


def test_idle_present_without_present_command(sim, tmp_path):
    data = P.clear(0x07E0) + P.rects([(2, 2, 8, 8, 0xF800)])
    got, _, _ = run_fw(sim, tmp_path, data, 64)
    assert got[5, 5] == 0xF800
    assert got[60, 100] == 0x07E0


def test_oversize_length_header_resyncs(sim, tmp_path):
    junk = bytes([0xA5, 0x5A, 0x02, 0xFF, 0xFF])
    data = junk + P.clear(0x07E0) + P.present()
    got, _, _ = run_fw(sim, tmp_path, data, 64)
    assert got[10, 10] == 0x07E0
