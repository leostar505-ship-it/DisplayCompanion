import http.server
import json
import threading

import numpy as np
import pytest

from screenlink.assistant import speech, voice, whispercpp
from screenlink.assistant.settings import Settings


def tone(chunks, amp=6000):
    t = np.arange(4000 * chunks)
    return (amp * np.sin(t * 0.3)).astype("<i2").tobytes()


def quiet(chunks):
    return (np.random.default_rng(1).normal(0, 20, 4000 * chunks)).astype("<i2").tobytes()


def split(pcm):
    return [pcm[i:i + 8000] for i in range(0, len(pcm), 8000)]


def test_clean_text_drops_bracketed_noise():
    assert whispercpp.clean_text(" [BLANK_AUDIO] hello (music)  there ") == "hello there"


def test_wav_and_multipart():
    wav = whispercpp.to_wav(b"\x00\x00" * 100)
    assert wav[:4] == b"RIFF"
    body, ctype = whispercpp.multipart({"a": "1"}, "x.wav", wav)
    assert b'name="a"' in body and wav in body and "boundary=" in ctype


def test_segmenter_finds_burst():
    seg = whispercpp.Segmenter()
    out = None
    for c in split(quiet(4)) + split(tone(4)) + split(quiet(6)):
        got = seg.feed(c)
        if got:
            out = got
    assert out is not None and len(out) >= 8000 * 4


def test_segmenter_ignores_silence():
    seg = whispercpp.Segmenter()
    assert all(seg.feed(c) is None for c in split(quiet(20)))


def test_server_transcribes_through_http():
    seen = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def do_POST(self):
            n = int(self.headers["Content-Length"])
            seen["body"] = self.rfile.read(n)
            out = json.dumps({"text": " Hello [BLANK_AUDIO] world "}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    server = whispercpp.Server(None, "m.bin", url="http://127.0.0.1:%d" % srv.server_port)
    assert server.transcribe(b"\x00\x00" * 160) == "Hello world"
    assert b"RIFF" in seen["body"]
    srv.shutdown()


def test_server_falls_back_to_cpu_when_gpu_launch_dies():
    launched = []

    class Dead:
        def poll(self):
            return 1

    class Alive:
        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, t):
            pass

    def launcher(cmd, **kw):
        launched.append(cmd)
        return Dead() if "-ng" not in cmd else Alive()

    class Opener:
        def __call__(self, *a, **k):
            class R:
                def __enter__(s):
                    return s

                def __exit__(s, *x):
                    pass
            return R()

    server = whispercpp.Server("x.exe", "m.bin", gpu=True, launcher=launcher, opener=Opener())
    server.start()
    assert "-ng" not in launched[0] and "-ng" in launched[1]
    assert server.used_gpu is False


class FakeEngine:
    def __init__(self):
        self.wake_calls = 0
        self.dict_calls = 0

    def preload_wake(self):
        pass

    def preload_dictation(self):
        pass

    def maintain(self):
        pass

    def close(self):
        pass

    def wake(self, pcm):
        self.wake_calls += 1
        return "Hey, Claude."

    def dictate(self, pcm):
        self.dict_calls += 1
        return "what is on my screen"


def test_whisper_listener_wake_then_dictation(monkeypatch):
    monkeypatch.setattr(speech, "DEAF_AFTER_WAKE", 0.0)
    events = []
    chunks = split(quiet(4)) + split(tone(4)) + split(quiet(6)) + split(quiet(2)) + split(tone(5)) + split(quiet(8))
    chunks += split(quiet(4))
    engine = FakeEngine()
    done = threading.Event()

    def on_text(t):
        events.append(("text", t))
        done.set()

    listener = speech.WhisperListener(lambda: events.append(("wake",)), on_text, lambda m: None, engine,
                                      source=iter(chunks))
    listener.start()
    assert done.wait(10)
    listener.stop()
    assert events[0] == ("wake",)
    assert ("text", "what is on my screen") in events


def test_whisper_listener_wake_with_command_in_same_breath(monkeypatch):
    monkeypatch.setattr(speech, "DEAF_AFTER_WAKE", 0.0)
    events = []
    engine = FakeEngine()
    engine.wake = lambda pcm: "Hey Claude what is the time"
    chunks = split(quiet(4)) + split(tone(4)) + split(quiet(8))
    done = threading.Event()
    listener = speech.WhisperListener(lambda: events.append("wake"), lambda t: (events.append(t), done.set()),
                                      lambda m: None, engine, source=iter(chunks))
    listener.start()
    assert done.wait(10)
    listener.stop()
    assert events == ["wake", "what is the time"]


def test_whisper_listener_silence_gives_empty_text(monkeypatch):
    monkeypatch.setattr(speech, "LISTEN_TIMEOUT", 0.0)
    monkeypatch.setattr(speech, "DEAF_AFTER_WAKE", 0.0)
    got = []
    done = threading.Event()
    engine = FakeEngine()
    listener = speech.WhisperListener(lambda: None, lambda t: (got.append(t), done.set()), lambda m: None, engine,
                                      source=iter(split(quiet(30))))
    listener.start()
    listener.dictate()
    assert done.wait(10)
    listener.stop()
    assert got[0] == ""


def test_after_wake():
    assert speech.after_wake("hey claude what's up") == "what's up"
    assert speech.after_wake("hey claude") == ""


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    s = Settings(tmp_path / "a.json")
    monkeypatch.setattr(whispercpp, "find_server", lambda: "whisper-server.exe")
    return s


def test_voice_requires_both_models_and_downloads_missing(cfg, monkeypatch):
    assert voice.engine_kind(cfg) == "whisper"
    keys = [m[0] for m in voice.missing(cfg)]
    assert keys == ["small.en", "large-v3-q5_0"]

    class Resp:
        headers = {"Content-Length": "10"}

        def __init__(self):
            self.data = b"x" * 10

        def read(self, n):
            d, self.data = self.data, b""
            return d

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(whispercpp, "MODELS", {k: (v[0], 0) for k, v in whispercpp.MODELS.items()})
    seen = []
    voice.download_missing(cfg, lambda f, label, i, n: seen.append((label, i, n)), opener=lambda *a, **k: Resp())
    assert voice.have_all(cfg)
    assert seen[-1][2] == 2


def test_voice_falls_back_to_vosk_without_binary(cfg, monkeypatch):
    monkeypatch.setattr(whispercpp, "find_server", lambda: None)
    assert voice.engine_kind(cfg) == "vosk"
    cfg.set("voice_engine", "vosk")
    assert voice.engine_kind(cfg) == "vosk"
