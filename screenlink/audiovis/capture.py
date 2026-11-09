import threading
import time

import numpy as np

from .analysis import FFT_SIZE, decimation_factor

AUTO_DEVICE = "Default output (auto)"


class RingBuffer:
    def __init__(self, size=FFT_SIZE, stale_after=0.12):
        self.size = size
        self.stale_after = stale_after
        self.data = np.zeros(size, dtype=np.float32)
        self.stamp = 0.0
        self.lock = threading.Lock()

    def push(self, samples):
        n = samples.size
        if n == 0:
            return
        with self.lock:
            if n >= self.size:
                self.data = samples[-self.size :].astype(np.float32, copy=True)
            else:
                self.data = np.concatenate((self.data[n:], samples.astype(np.float32, copy=False)))
            self.stamp = time.monotonic()

    def age(self):
        with self.lock:
            if self.stamp == 0.0:
                return float("inf")
            return time.monotonic() - self.stamp

    def latest(self):
        with self.lock:
            fresh = self.stamp != 0.0 and time.monotonic() - self.stamp <= self.stale_after
            data = self.data.copy()
        if not fresh:
            return np.zeros(self.size, dtype=np.float32)
        return data


class LoopbackCapture:
    def __init__(self):
        self.buffer = RingBuffer()
        self.rate = 48000.0
        self.status = "Starting audio capture"
        self._pa = None
        self._stream = None
        self._pyaudio = None
        self._factor = 1
        self._channels = 2
        self._carry = np.zeros(0, dtype=np.float32)
        self._device = None
        self._names = []
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._open()
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def is_silent(self):
        return self.buffer.age() > 1.0

    def latest(self):
        return self.buffer.latest()

    def devices(self):
        return [AUTO_DEVICE] + list(self._names)

    def select(self, name):
        self._device = None if (not name or name == AUTO_DEVICE) else name
        self.restart()

    def restart(self):
        threading.Thread(target=self._open, daemon=True).start()

    def close(self):
        self._stop.set()
        with self._lock:
            self._close_stream()

    def _pick(self, pa, pyaudio):
        loopbacks = list(pa.get_loopback_device_info_generator())
        self._names = [d["name"] for d in loopbacks]
        if self._device:
            for d in loopbacks:
                if d["name"] == self._device:
                    return d
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_out = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        if default_out.get("isLoopbackDevice"):
            return default_out
        for d in loopbacks:
            if default_out["name"] in d["name"]:
                return d
        return loopbacks[0] if loopbacks else None

    def _open(self):
        with self._lock:
            self._close_stream()
            try:
                import pyaudiowpatch as pyaudio
            except ImportError:
                self.status = "PyAudioWPatch is not installed (Windows only)"
                return False
            try:
                self._pyaudio = pyaudio
                self._pa = pyaudio.PyAudio()
                info = self._pick(self._pa, pyaudio)
                if info is None:
                    self.status = "No audio output device found"
                    self._close_stream()
                    return False
                channels = max(1, int(info["maxInputChannels"]))
                native_rate = int(info["defaultSampleRate"])
                self._factor = decimation_factor(native_rate)
                self._channels = channels
                self._carry = np.zeros(0, dtype=np.float32)
                self.rate = native_rate / self._factor
                self._stream = self._pa.open(
                    format=pyaudio.paInt16,
                    channels=channels,
                    rate=native_rate,
                    frames_per_buffer=1024,
                    input=True,
                    input_device_index=info["index"],
                    stream_callback=self._callback,
                )
                self.status = "Listening: " + info["name"]
                return True
            except Exception as exc:
                self.status = "Audio error: " + str(exc)
                self._close_stream()
                return False

    def _callback(self, in_data, frame_count, time_info, status_flags):
        samples = np.frombuffer(in_data, dtype=np.int16).astype(np.float32) / 32768.0
        self._push(samples)
        return (None, self._pyaudio.paContinue)

    def _push(self, samples):
        channels = self._channels
        if channels > 1:
            usable = (samples.size // channels) * channels
            samples = samples[:usable].reshape(-1, channels).mean(axis=1)
        factor = self._factor
        if factor > 1:
            if self._carry.size:
                samples = np.concatenate((self._carry, samples))
            usable = (samples.size // factor) * factor
            self._carry = samples[usable:]
            samples = samples[:usable].reshape(-1, factor).mean(axis=1)
        self.buffer.push(samples)

    def _close_stream(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        pa, self._pa = self._pa, None
        if pa is not None:
            try:
                pa.terminate()
            except Exception:
                pass

    def _watch(self):
        wait = 3.0
        quiet_since = time.monotonic()
        while not self._stop.wait(0.5):
            if self.buffer.age() < 1.0:
                wait = 3.0
                quiet_since = time.monotonic()
                continue
            if time.monotonic() - quiet_since >= wait:
                self._open()
                wait = min(wait * 2.0, 15.0)
                quiet_since = time.monotonic()


class DemoSource:
    def __init__(self):
        self.rate = 48000.0
        self.status = "Demo audio (synthetic)"
        self.start = time.perf_counter()
        self.rng = np.random.default_rng(1)

    def is_silent(self):
        return False

    def devices(self):
        return []

    def select(self, name):
        pass

    def restart(self):
        pass

    def close(self):
        pass

    def latest(self):
        t_end = time.perf_counter() - self.start
        t = t_end - np.arange(FFT_SIZE)[::-1] / self.rate
        beat = np.mod(t, 0.5)
        kick = 0.8 * np.exp(-beat * 14.0) * np.sin(2.0 * np.pi * 55.0 * beat)
        off = np.mod(t + 0.25, 1.0)
        snare = 0.35 * np.exp(-off * 16.0) * self.rng.uniform(-1.0, 1.0, FFT_SIZE)
        hat_phase = np.mod(t, 0.125)
        hat = 0.12 * np.exp(-hat_phase * 70.0) * self.rng.uniform(-1.0, 1.0, FFT_SIZE)
        gate = (np.mod(t, 2.0) < 1.5).astype(np.float64)
        lead = 0.2 * gate * np.sin(2.0 * np.pi * (330.0 + 110.0 * np.sin(t * 0.7)) * t)
        step = np.floor(t / 0.25).astype(np.int64)
        notes = np.array([110.0, 138.6, 164.8, 220.0, 277.2, 329.6, 440.0, 554.4])
        base = notes[step % len(notes)]
        env = np.exp(-np.mod(t, 0.25) * 6.0)
        arp = np.zeros(FFT_SIZE)
        for harmonic in (1, 2, 3, 5, 8, 13):
            arp += np.sin(2.0 * np.pi * base * harmonic * t) / harmonic
        arp *= 0.12 * env
        return np.clip(kick + snare + hat + lead + arp, -1.0, 1.0).astype(np.float32)
