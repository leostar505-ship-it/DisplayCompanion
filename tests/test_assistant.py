import io
import json
import time
import urllib.error

import pytest
from PIL import Image

from screenlink import fonts
from screenlink.assistant import api, cues, hotkey, hudart, speech, typer
from screenlink.assistant.screenshot import encode
from screenlink.assistant.settings import DEFAULTS, Settings


class FakeResp:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_settings_roundtrip(tmp_path):
    s = Settings(tmp_path / "a.json")
    assert s.get("model") == DEFAULTS["model"]
    s.set("api_key", "sk-test")
    s.set("font_size", 14)
    s.set("nope", 1)
    assert s.save()
    t = Settings(tmp_path / "a.json")
    assert t.get("api_key") == "sk-test"
    assert t.get("font_size") == 14
    assert "nope" not in t.data


def test_settings_ignores_bad_types(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"font_size": "huge", "typing_cps": 40, "hud_scale": 2}))
    s = Settings(tmp_path / "a.json")
    assert s.get("font_size") == DEFAULTS["font_size"]
    assert s.get("typing_cps") == 40
    assert s.get("hud_scale") == 2.0


def test_api_key_env_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "envkey")
    s = Settings(tmp_path / "a.json")
    assert s.api_key() == "envkey"
    s.set("api_key", "  mine ")
    assert s.api_key() == "mine"


def test_body_has_suffix_image_and_limit():
    body = api.build_body("m", "what is this?", "AAAA", 200, [("user", "hi"), ("assistant", "hello")])
    assert body["model"] == "m"
    assert "200 characters" in body["system"]
    last = body["messages"][-1]["content"]
    assert last[0]["type"] == "image" and last[0]["source"]["data"] == "AAAA"
    assert last[1]["text"].endswith(api.SUFFIX)
    assert body["messages"][0] == {"role": "user", "content": "hi"}


def test_body_without_image():
    body = api.build_body("m", "q", None, 100, [])
    assert [b["type"] for b in body["messages"][-1]["content"]] == ["text"]


def test_ask_success_and_cleaning():
    seen = {}

    def opener(req, timeout=0):
        seen["headers"] = dict(req.header_items())
        seen["body"] = json.loads(req.data)
        return FakeResp({"content": [{"type": "text", "text": "**Yes**, it is.\n\n- fine"}]})

    out = api.ask("k", "m", "q", None, 100, opener=opener)
    assert out == "Yes, it is.\nfine"
    assert seen["headers"]["X-api-key"] == "k"
    assert seen["headers"]["Anthropic-version"] == api.VERSION


def test_ask_errors():
    with pytest.raises(api.AssistantError, match="No API key"):
        api.ask("", "m", "q", None, 100)

    def http401(req, timeout=0):
        raise urllib.error.HTTPError("u", 401, "x", {}, io.BytesIO(b'{"error":{"message":"bad"}}'))

    with pytest.raises(api.AssistantError, match="rejected"):
        api.ask("k", "m", "q", None, 100, opener=http401)

    def offline(req, timeout=0):
        raise urllib.error.URLError("no route")

    with pytest.raises(api.AssistantError, match="Could not reach"):
        api.ask("k", "m", "q", None, 100, opener=offline)

    def empty(req, timeout=0):
        return FakeResp({"content": []})

    with pytest.raises(api.AssistantError, match="empty"):
        api.ask("k", "m", "q", None, 100, opener=empty)


def test_fit_chars():
    assert api.fit_chars("short", 20) == "short"
    out = api.fit_chars("word " * 40, 50)
    assert len(out) <= 53 and out.endswith("...")


def test_screenshot_encode_downsizes():
    import base64
    data = base64.b64decode(encode(Image.new("RGB", (3200, 1800), (5, 6, 7))))
    img = Image.open(io.BytesIO(data))
    assert max(img.size) == 1568


def test_cues_render_all():
    for kind in cues.CUES:
        data = cues.render(kind)
        assert data[:4] == b"RIFF" and len(data) > 10000


def test_hotkey_parse():
    assert hotkey.parse("ctrl+alt+c") == (0x3, ord("C"))
    assert hotkey.parse("Win + F9") == (0x8, 0x78)
    assert hotkey.parse("ctrl+space") == (0x2, 0x20)
    assert hotkey.parse("c") is None
    assert hotkey.parse("ctrl+alt") is None
    assert hotkey.parse("ctrl+a+b") is None
    assert hotkey.parse("") is None


def test_hotkey_start_rejects_bad_spec():
    h = hotkey.Hotkey()
    assert not h.start("c", lambda: None)
    assert "ctrl" in h.error


def test_is_wake():
    assert speech.is_wake("hey claude")
    assert speech.is_wake("okay cloud")
    assert speech.is_wake("so hey claude what")
    assert not speech.is_wake("claude")
    assert not speech.is_wake("hey there")
    assert not speech.is_wake("")


def test_resample_and_mono():
    import numpy as np
    stereo = np.array([100, 300, 200, 400], dtype="<i2").tobytes()
    assert np.frombuffer(speech.to_mono(stereo, 2), dtype="<i2").tolist() == [200, 300]
    mono = np.arange(480, dtype="<i2").tobytes()
    out = speech.resample(mono, 48000, 16000)
    assert len(out) == 160 * 2


class FakeRec:
    def __init__(self, model, rate, grammar=None):
        self.grammar = grammar
        self.n = 0

    def AcceptWaveform(self, data):
        self.n += 1
        if self.grammar is None:
            return self.n >= 3
        return False

    def Result(self):
        return json.dumps({"text": "what is the time"})

    def PartialResult(self):
        if self.grammar is not None:
            return json.dumps({"partial": "hey claude" if self.n >= 2 else ""})
        return json.dumps({"partial": "what"})

    def FinalResult(self):
        return self.Result()

    def Reset(self):
        self.n = 0


class FakeVosk:
    Model = staticmethod(lambda path: object())
    KaldiRecognizer = FakeRec


def test_listener_wake_then_text(monkeypatch):
    monkeypatch.setattr(speech, "DEAF_AFTER_WAKE", 0.0)
    got = {"wake": 0, "text": [], "status": []}
    chunks = [b"\0\0"] * 40

    def slow():
        for c in chunks:
            yield c
            time.sleep(0.02)

    lis = speech.Listener(lambda: got.__setitem__("wake", got["wake"] + 1), got["text"].append,
                          got["status"].append, vosk_module=FakeVosk, source=slow())
    lis.start()
    lis.thread.join(5)
    assert got["wake"] >= 1
    assert got["text"][0] == "what is the time"


def test_listener_dictate_on_request(monkeypatch):
    monkeypatch.setattr(speech, "DEAF_AFTER_WAKE", 0.0)
    got = {"text": []}

    def slow():
        for _ in range(30):
            yield b"\0\0"
            time.sleep(0.02)

    lis = speech.Listener(lambda: None, got["text"].append, lambda m: None, wake_enabled=False,
                          vosk_module=FakeVosk, source=slow())
    lis.dictate()
    lis.start()
    lis.thread.join(5)
    assert got["text"][0] == "what is the time"


def test_type_schedule():
    sch = typer.TypeSchedule("Hello there. Ok", 30)
    assert sch.size == 15
    assert sch.count(0) == 0
    assert sch.count(sch.total + 1) == 15
    mid = sch.count(sch.total / 2)
    assert 0 < mid < 15
    assert typer.TypeSchedule("abc", 30, seed=1).times == typer.TypeSchedule("abc", 30, seed=1).times


def test_fit_reply_fits_screen():
    font = fonts.load_font(None, 11)
    long = "This is a long answer that keeps going and going. " * 20
    out = typer.fit_reply(long, font)
    lines, rows = fonts.layout(out, font)
    assert len(lines) <= rows
    assert out.endswith("...")
    assert typer.fit_reply("Short.", font) == "Short."
    assert typer.capacity(font) > 50


def test_hud_card_renders_every_kind():
    card = hudart.Card(1.0)
    for kind in hudart.KINDS:
        for t in (0.0, 0.7, 2.2, 3.4, 5.6):
            img = card.render(kind, t, t + 1.0, 0.5, 1.0)
            assert img.size == (card.w, card.h)
    img = card.render("listening", 1.0, 1.0)
    assert img.getpixel((2, 2)) == hudart.KEY or sum(img.getpixel((0, 0))) < 40


class FakeRun:
    def __init__(self, out="", err="", code=0):
        self.stdout, self.stderr, self.returncode = out, err, code


def test_claude_code_ask_builds_command_and_reads_image():
    from screenlink.assistant import claude_code
    seen = {}

    def runner(cmd, prompt, cwd, timeout):
        import os
        seen["cmd"], seen["prompt"] = cmd, prompt
        seen["file"] = os.path.exists(os.path.join(cwd, "screen.jpg"))
        return FakeRun("**Fine** answer\n")

    img = encode(Image.new("RGB", (40, 30), (1, 2, 3)))
    out = claude_code.ask("claude-haiku-5-5", "what is this?", img, 120, [("user", "hi"), ("assistant", "yo")],
                          runner=runner, exe="claude")
    assert out == "Fine answer"
    assert seen["cmd"][:4] == ["claude", "-p", "--model", "haiku"]
    assert "--allowedTools" in seen["cmd"] and seen["file"]
    assert "120 characters" in seen["prompt"] and "screen.jpg" in seen["prompt"]
    assert seen["prompt"].rstrip().endswith(api.SUFFIX)
    assert "User: hi" in seen["prompt"]


def test_claude_code_no_image_has_no_tools():
    from screenlink.assistant import claude_code
    seen = {}

    def runner(cmd, prompt, cwd, timeout):
        seen["cmd"] = cmd
        return FakeRun("ok")

    claude_code.ask("m", "q", None, 50, runner=runner, exe="claude")
    assert "--allowedTools" not in seen["cmd"]


def test_claude_code_errors(monkeypatch):
    from screenlink.assistant import claude_code
    monkeypatch.setattr(claude_code, "find", lambda: None)
    with pytest.raises(api.AssistantError, match="not found"):
        claude_code.ask("m", "q", None, 50, runner=lambda *a: FakeRun("x"))
    with pytest.raises(api.AssistantError, match="not signed in"):
        claude_code.ask("m", "q", None, 50, runner=lambda *a: FakeRun("", "Please login first", 1), exe="claude")
    with pytest.raises(api.AssistantError, match="failed"):
        claude_code.ask("m", "q", None, 50, runner=lambda *a: FakeRun("", "boom", 2), exe="claude")
