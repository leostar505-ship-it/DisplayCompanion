import threading
import time

import numpy as np


class DemoSource:
    name = "Demo signal"
    rate = 48000

    def __init__(self):
        self.started = time.perf_counter()
        self.error = ""

    def start(self):
        return True

    def stop(self):
        pass

    def read(self, count):
        end = time.perf_counter() - self.started
        t = end - (np.arange(count)[::-1] / self.rate)
        beat = np.clip(np.sin(2 * np.pi * 2.0 * t), 0, 1) ** 3
        bass = 0.6 * beat * np.sin(2 * np.pi * 70 * t)
        sweep_f = 200 + 3800 * (0.5 + 0.5 * np.sin(2 * np.pi * t / 7.0))
        sweep = 0.25 * np.sin(2 * np.pi * np.cumsum(sweep_f) / self.rate + 6.0 * t)
        hat_env = np.clip(np.sin(2 * np.pi * 4.0 * t + 1.0), 0, 1) ** 8
        hat = 0.2 * hat_env * np.random.uniform(-1, 1, count)
        mid = 0.2 * np.sin(2 * np.pi * 523 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * t / 3.0))
        return (bass + sweep + hat + mid).astype(np.float32)


class LoopbackCapture:
    name = "System audio (WASAPI loopback)"

    def __init__(self, seconds=1.0):
        self.rate = 48000
        self.error = ""
        self._pa = None
        self._stream = None
        self._lock = threading.Lock()
        self._ring = np.zeros(int(self.rate * seconds), dtype=np.float32)
        self._seconds = seconds

    def start(self):
        try:
            import pyaudiowpatch as pyaudio
        except Exception as exc:
            self.error = "pyaudiowpatch not installed (%s)" % exc
            return False
        try:
            self._pa = pyaudio.PyAudio()
            wasapi = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            speakers = self._pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
            if not speakers.get("isLoopbackDevice"):
                for loop in self._pa.get_loopback_device_info_generator():
                    if speakers["name"] in loop["name"]:
                        speakers = loop
                        break
            self.rate = int(speakers["defaultSampleRate"])
            channels = max(1, int(speakers["maxInputChannels"]))
            self._ring = np.zeros(int(self.rate * self._seconds), dtype=np.float32)

            def callback(data, frames, info, status):
                block = np.frombuffer(data, dtype=np.float32).reshape(-1, channels).mean(axis=1)
                with self._lock:
                    n = len(block)
                    if n >= len(self._ring):
                        self._ring[:] = block[-len(self._ring):]
                    else:
                        self._ring = np.roll(self._ring, -n)
                        self._ring[-n:] = block
                return (None, pyaudio.paContinue)

            self._stream = self._pa.open(
                format=pyaudio.paFloat32,
                channels=channels,
                rate=self.rate,
                input=True,
                input_device_index=speakers["index"],
                frames_per_buffer=1024,
                stream_callback=callback,
            )
            return True
        except Exception as exc:
            self.error = str(exc)
            self.stop()
            return False

    def stop(self):
        try:
            if self._stream is not None:
                self._stream.stop_stream()
                self._stream.close()
        except Exception:
            pass
        try:
            if self._pa is not None:
                self._pa.terminate()
        except Exception:
            pass
        self._stream = None
        self._pa = None

    def read(self, count):
        with self._lock:
            return self._ring[-count:].copy()


def make_source(kind):
    if kind == "demo":
        src = DemoSource()
        src.start()
        return src
    src = LoopbackCapture()
    if src.start():
        return src
    fallback = DemoSource()
    fallback.error = src.error
    fallback.name = "Demo signal (loopback unavailable)"
    return fallback
