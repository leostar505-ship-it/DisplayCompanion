import json
import os
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile

import numpy as np

from .settings import config_dir
from .smartshot import is_cancel

MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_URL = "https://alphacephei.com/vosk/models/%s.zip" % MODEL_NAME
WAKE_GRAMMAR = json.dumps([
    "hey claude", "hey cloud", "hey claud", "hey clod", "hey clawed", "hey clawd",
    "okay claude", "ok claude", "hi claude", "hello claude", "[unk]",
])
GREETINGS = {"hey", "hay", "hi", "hello", "okay", "ok", "a"}
NAMES = {"claude", "claud", "cloud", "clod", "clawed", "clawd", "clode", "claudia"}
RATE = 16000
CHUNK = 4000
LISTEN_TIMEOUT = 6.0
MAX_DICTATION = 20.0
DEAF_AFTER_WAKE = 0.4


def model_dir():
    return config_dir() / "models" / MODEL_NAME


def have_model():
    folder = model_dir()
    return folder.is_dir() and (folder / "am").exists()


def download_model(progress=None, opener=None):
    open_url = opener or urllib.request.urlopen
    target = model_dir()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "model.zip")
        with open_url(MODEL_URL, timeout=60) as resp, open(archive, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                block = resp.read(1 << 16)
                if not block:
                    break
                out.write(block)
                done += len(block)
                if progress and total:
                    progress(done / total)
        extract = os.path.join(tmp, "x")
        with zipfile.ZipFile(archive) as z:
            z.extractall(extract)
        inner = os.path.join(extract, MODEL_NAME)
        if not os.path.isdir(inner):
            raise RuntimeError("The voice model download was not what I expected.")
        if target.exists():
            shutil.rmtree(target)
        shutil.move(inner, str(target))
    if progress:
        progress(1.0)


def is_wake(text):
    words = text.lower().replace(",", " ").split()
    if not any(w in NAMES for w in words):
        return False
    for i, w in enumerate(words):
        if w in NAMES:
            return i > 0 and words[i - 1] in GREETINGS
    return False


def resample(data, src_rate, dst_rate=RATE):
    if src_rate == dst_rate:
        return data
    samples = np.frombuffer(data, dtype="<i2")
    if len(samples) == 0:
        return data
    n = int(len(samples) * dst_rate / float(src_rate))
    x = np.linspace(0, len(samples) - 1, n)
    return np.interp(x, np.arange(len(samples)), samples).astype("<i2").tobytes()


def to_mono(data, channels):
    if channels == 1:
        return data
    samples = np.frombuffer(data, dtype="<i2")
    usable = len(samples) - len(samples) % channels
    return samples[:usable].reshape(-1, channels).mean(axis=1).astype("<i2").tobytes()


class Listener:
    def __init__(self, on_wake, on_text, on_status, wake_enabled=True, vosk_module=None, source=None):
        self.on_wake = on_wake
        self.on_text = on_text
        self.on_status = on_status
        self.wake_enabled = wake_enabled
        self.vosk = vosk_module
        self.source = source
        self.thread = None
        self.stop_flag = threading.Event()
        self.mode = "wake"
        self.paused = False
        self.dictate_requested = False
        self.lock = threading.Lock()

    def start(self):
        if self.thread is not None:
            return
        self.stop_flag.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_flag.set()
        if self.thread is not None:
            self.thread.join(2.0)
        self.thread = None

    def pause(self, value):
        self.paused = bool(value)

    def dictate(self):
        self.dictate_requested = True

    def _chunks(self):
        import pyaudiowpatch as pyaudio
        pa = pyaudio.PyAudio()
        try:
            info = pa.get_default_input_device_info()
            rate = int(info.get("defaultSampleRate", RATE))
            channels = max(1, min(2, int(info.get("maxInputChannels", 1))))
            index = info["index"]
            try:
                stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True,
                                 frames_per_buffer=CHUNK, input_device_index=index)
                native = (RATE, 1)
            except OSError:
                stream = pa.open(format=pyaudio.paInt16, channels=channels, rate=rate, input=True,
                                 frames_per_buffer=int(CHUNK * rate / RATE), input_device_index=index)
                native = (rate, channels)
            try:
                while not self.stop_flag.is_set():
                    data = stream.read(int(CHUNK * native[0] / RATE), exception_on_overflow=False)
                    yield resample(to_mono(data, native[1]), native[0])
            finally:
                stream.stop_stream()
                stream.close()
        finally:
            pa.terminate()

    def _load(self):
        if self.vosk is None:
            import vosk
            vosk.SetLogLevel(-1)
            self.vosk = vosk
        return self.vosk.Model(str(model_dir()))

    def _run(self):
        try:
            model = self._load()
        except Exception as exc:
            self.on_status("Voice model problem: %s" % exc)
            return
        vosk = self.vosk
        wake_rec = vosk.KaldiRecognizer(model, RATE, WAKE_GRAMMAR)
        dict_rec = None
        started = 0.0
        heard = False
        deaf_until = 0.0
        try:
            chunks = self.source if self.source is not None else self._chunks()
            for data in chunks:
                if self.stop_flag.is_set():
                    break
                now = time.monotonic()
                if self.paused or now < deaf_until:
                    continue
                if self.mode == "wake":
                    if self.dictate_requested:
                        self.dictate_requested = False
                        self.mode = "dictate"
                        dict_rec = vosk.KaldiRecognizer(model, RATE)
                        started = now
                        heard = False
                        deaf_until = now + DEAF_AFTER_WAKE
                        continue
                    if not self.wake_enabled:
                        continue
                    fired = False
                    if wake_rec.AcceptWaveform(data):
                        fired = is_wake(json.loads(wake_rec.Result()).get("text", ""))
                    else:
                        fired = is_wake(json.loads(wake_rec.PartialResult()).get("partial", ""))
                    if fired:
                        wake_rec.Reset()
                        self.mode = "dictate"
                        dict_rec = vosk.KaldiRecognizer(model, RATE)
                        started = now
                        heard = False
                        deaf_until = now + DEAF_AFTER_WAKE
                        self.on_wake()
                    continue
                final = None
                if dict_rec.AcceptWaveform(data):
                    final = json.loads(dict_rec.Result()).get("text", "").strip()
                else:
                    if json.loads(dict_rec.PartialResult()).get("partial", "").strip():
                        heard = True
                if final is None and not heard and now - started > LISTEN_TIMEOUT:
                    final = ""
                if final is None and now - started > MAX_DICTATION:
                    final = json.loads(dict_rec.FinalResult()).get("text", "").strip()
                if final is not None:
                    self.mode = "wake"
                    wake_rec.Reset()
                    self.on_text(final)
        except Exception as exc:
            self.on_status("Microphone problem: %s" % exc)


def after_wake(text):
    words = text.replace(",", " ").replace(".", " ").replace("!", " ").replace("?", " ").split()
    for i, w in enumerate(words):
        if w.lower() in NAMES:
            return " ".join(words[i + 1:]).strip()
    return ""


def normalise(text):
    return "".join(ch if ch.isalnum() or ch.isspace() or ch in "'," else " " for ch in text.lower())


class WhisperListener(Listener):
    def __init__(self, on_wake, on_text, on_status, engine, wake_enabled=True, source=None):
        super().__init__(on_wake, on_text, on_status, wake_enabled=wake_enabled, source=source)
        self.engine = engine

    def _run(self):
        from .whispercpp import Segmenter, WhisperError
        engine = self.engine
        try:
            self.on_status("Loading the voice engine...")
            if self.wake_enabled:
                engine.preload_wake()
            else:
                engine.preload_dictation()
            self.on_status("Voice engine ready.")
        except Exception as exc:
            self.on_status("Voice engine problem: %s" % exc)
            return
        wake_seg = Segmenter(end_quiet=3, min_voiced=2, max_chunks=20)
        talk_seg = Segmenter(end_quiet=4, min_voiced=2, max_chunks=int(MAX_DICTATION / 0.25))
        started = 0.0
        deaf_until = 0.0
        last_maintain = 0.0
        try:
            chunks = self.source if self.source is not None else self._chunks()
            for data in chunks:
                if self.stop_flag.is_set():
                    break
                now = time.monotonic()
                if now - last_maintain > 30:
                    last_maintain = now
                    engine.maintain()
                if self.paused or now < deaf_until:
                    continue
                if self.mode == "wake":
                    if self.dictate_requested:
                        self.dictate_requested = False
                        self.mode = "dictate"
                        talk_seg.reset()
                        started = now
                        deaf_until = now + DEAF_AFTER_WAKE
                        continue
                    if not self.wake_enabled:
                        continue
                    seg = wake_seg.feed(data)
                    if seg is None:
                        continue
                    try:
                        text = engine.wake(seg)
                    except WhisperError as exc:
                        self.on_status("Voice engine problem: %s" % exc)
                        continue
                    if is_wake(normalise(text)):
                        rest = after_wake(normalise(text))
                        self.on_wake()
                        if len(rest.split()) >= 3 or is_cancel(rest):
                            self.on_text(rest)
                            continue
                        self.mode = "dictate"
                        talk_seg.reset()
                        started = time.monotonic()
                        deaf_until = started + DEAF_AFTER_WAKE
                    continue
                seg = talk_seg.feed(data)
                if seg is None:
                    if not talk_seg.active and now - started > LISTEN_TIMEOUT:
                        self.mode = "wake"
                        wake_seg.reset()
                        self.on_text("")
                    continue
                try:
                    final = engine.dictate(seg)
                except WhisperError as exc:
                    self.on_status("Voice engine problem: %s" % exc)
                    final = ""
                self.mode = "wake"
                wake_seg.reset()
                self.on_text(final)
        except Exception as exc:
            self.on_status("Microphone problem: %s" % exc)
        finally:
            engine.close()
