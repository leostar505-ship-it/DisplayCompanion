import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave

import numpy as np

from .settings import config_dir

HF_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/%s"

MODELS = {
    "large-v3": ("ggml-large-v3.bin", 3100),
    "large-v3-q5_0": ("ggml-large-v3-q5_0.bin", 1080),
    "large-v3-turbo": ("ggml-large-v3-turbo.bin", 1620),
    "large-v3-turbo-q5_0": ("ggml-large-v3-turbo-q5_0.bin", 570),
    "medium.en": ("ggml-medium.en.bin", 1530),
    "small.en": ("ggml-small.en.bin", 470),
    "base.en": ("ggml-base.en.bin", 142),
}
DICTATION_CHOICES = ["large-v3-q5_0", "large-v3", "large-v3-turbo", "large-v3-turbo-q5_0", "medium.en", "small.en"]
WAKE_CHOICES = ["small.en", "base.en", "medium.en"]
RATE = 16000
IDLE_UNLOAD = 600.0
START_TIMEOUT = 180.0


class WhisperError(Exception):
    pass


def models_dir():
    return config_dir() / "models" / "whisper"


def model_path(name):
    return models_dir() / MODELS[name][0]


def have_model(name):
    path = model_path(name)
    minimum = MODELS[name][1] * 1024 * 1024 * 0.9
    return path.is_file() and path.stat().st_size >= minimum


def model_size_mb(name):
    return MODELS[name][1]


def download_model(name, progress=None, opener=None):
    open_url = opener or urllib.request.urlopen
    path = model_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".part")
    url = HF_URL % MODELS[name][0]
    with open_url(url, timeout=60) as resp, open(part, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            block = resp.read(1 << 20)
            if not block:
                break
            out.write(block)
            done += len(block)
            if progress and total:
                progress(done / total)
    if total and os.path.getsize(part) < total:
        os.remove(part)
        raise WhisperError("The download was cut short. Try again.")
    os.replace(part, path)
    if progress:
        progress(1.0)


def find_server():
    names = ["whisper-server.exe", "whisper-server"] if sys.platform == "win32" else ["whisper-server"]
    roots = []
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        roots.append(os.path.join(bundled, "whisper"))
    roots.append(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "whisper"))
    roots.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vendor", "whisper"))
    for root in roots:
        for name in names:
            path = os.path.normpath(os.path.join(root, name))
            if os.path.isfile(path):
                return path
    return None


def to_wav(pcm):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def multipart(fields, file_name, file_bytes):
    boundary = "----dc" + uuid.uuid4().hex
    parts = []
    for key, value in fields.items():
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, key, value)).encode())
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
                  "Content-Type: audio/wav\r\n\r\n" % (boundary, file_name)).encode())
    parts.append(file_bytes)
    parts.append(("\r\n--%s--\r\n" % boundary).encode())
    return b"".join(parts), "multipart/form-data; boundary=%s" % boundary


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def clean_text(text):
    out = []
    depth = 0
    for ch in str(text):
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return " ".join("".join(out).split()).strip()


class Server:
    def __init__(self, exe, model, gpu=True, url=None, launcher=None, opener=None):
        self.exe = exe
        self.model = str(model)
        self.gpu = gpu
        self.url = url
        self.launcher = launcher or subprocess.Popen
        self.opener = opener or urllib.request.urlopen
        self.proc = None
        self.lock = threading.Lock()
        self.last_used = time.monotonic()
        self.used_gpu = gpu

    @property
    def running(self):
        if self.url and self.proc is None:
            return True
        return self.proc is not None and self.proc.poll() is None

    def _launch(self, gpu):
        port = free_port()
        cmd = [self.exe, "-m", self.model, "--host", "127.0.0.1", "--port", str(port), "-l", "en"]
        if not gpu:
            cmd.append("-ng")
        flags = 0x08000000 if sys.platform == "win32" else 0
        self.proc = self.launcher(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  stdin=subprocess.DEVNULL, creationflags=flags)
        self.url = "http://127.0.0.1:%d" % port
        self.used_gpu = gpu

    def _ready(self, deadline):
        while time.monotonic() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                return False
            try:
                with self.opener(self.url + "/", timeout=2):
                    return True
            except urllib.error.HTTPError:
                return True
            except (urllib.error.URLError, OSError):
                time.sleep(0.4)
        return False

    def start(self):
        with self.lock:
            if self.running:
                return
            if self.exe is None:
                raise WhisperError("The Whisper program was not found.")
            order = [True, False] if self.gpu else [False]
            for gpu in order:
                self._launch(gpu)
                if self._ready(time.monotonic() + START_TIMEOUT):
                    return
                self._kill()
            raise WhisperError("The Whisper program would not start.")

    def _kill(self):
        proc = self.proc
        self.proc = None
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def stop(self):
        with self.lock:
            self._kill()

    def transcribe(self, pcm, timeout=90):
        if not self.running:
            self.start()
        body, ctype = multipart({"temperature": "0.0", "response_format": "json", "language": "en"},
                                "audio.wav", to_wav(pcm))
        req = urllib.request.Request(self.url + "/inference", data=body, headers={"Content-Type": ctype})
        try:
            with self.opener(req, timeout=timeout) as resp:
                raw = resp.read()
        except (urllib.error.URLError, OSError) as exc:
            raise WhisperError("The Whisper program stopped answering: %s" % exc)
        self.last_used = time.monotonic()
        try:
            return clean_text(json.loads(raw.decode("utf-8", "replace")).get("text", ""))
        except ValueError:
            raise WhisperError("Whisper sent something unreadable.")


class Segmenter:
    def __init__(self, end_quiet=3, min_voiced=2, max_chunks=24, floor=300.0):
        self.end_quiet = end_quiet
        self.min_voiced = min_voiced
        self.max_chunks = max_chunks
        self.floor = floor
        self.noise = floor
        self.reset()

    def reset(self):
        self.pre = []
        self.buf = []
        self.voiced = 0
        self.quiet = 0
        self.active = False

    def threshold(self):
        return max(self.floor, self.noise * 2.6)

    def feed(self, data):
        samples = np.frombuffer(data, dtype="<i2").astype(np.float64)
        rms = float(np.sqrt(np.mean(samples * samples))) if len(samples) else 0.0
        loud = rms > self.threshold()
        if not self.active and not loud:
            self.noise = self.noise * 0.9 + rms * 0.1
        if not self.active:
            self.pre.append(data)
            self.pre = self.pre[-2:]
            if loud:
                self.voiced += 1
                if self.voiced >= self.min_voiced:
                    self.active = True
                    self.buf = list(self.pre)
                    self.quiet = 0
            else:
                self.voiced = 0
            return None
        self.buf.append(data)
        self.quiet = 0 if loud else self.quiet + 1
        if self.quiet >= self.end_quiet or len(self.buf) >= self.max_chunks:
            out = b"".join(self.buf)
            self.reset()
            return out
        return None


class Engine:
    def __init__(self, exe, wake_model, dictation_model, gpu=True, server_factory=None):
        make = server_factory or Server
        self.wake_server = make(exe, model_path(wake_model), gpu)
        self.dict_server = make(exe, model_path(dictation_model), gpu)

    def wake(self, pcm):
        return self.wake_server.transcribe(pcm, timeout=30)

    def dictate(self, pcm):
        return self.dict_server.transcribe(pcm)

    def preload_wake(self):
        self.wake_server.start()

    def preload_dictation(self):
        self.dict_server.start()

    def maintain(self):
        server = self.dict_server
        if server.running and server.proc is not None and time.monotonic() - server.last_used > IDLE_UNLOAD:
            server.stop()

    def close(self):
        self.wake_server.stop()
        self.dict_server.stop()
