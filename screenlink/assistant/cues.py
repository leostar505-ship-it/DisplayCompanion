import io
import math
import os
import struct
import sys
import tempfile
import wave

import numpy as np

RATE = 44100

CUES = {
    "listening": ((660, 0.0, 110, 0.35, 4), (990, 0.11, 220, 0.35, 5)),
    "screenshot": ((988, 0.0, 80, 0.35, 5), (1319, 0.08, 200, 0.35, 5)),
    "thinking": ((784, 0.0, 100, 0.35, 4), (659, 0.1, 100, 0.35, 4), (784, 0.2, 200, 0.35, 5)),
    "responding": ((523, 0.0, 90, 0.35, 3), (659, 0.09, 90, 0.35, 3), (784, 0.18, 90, 0.35, 3),
                   (1047, 0.27, 200, 0.35, 5)),
    "done": ((659, 0.0, 420, 0.22, 3), (784, 0.02, 420, 0.22, 3), (988, 0.04, 420, 0.22, 3),
             (1319, 0.16, 560, 0.2, 4)),
    "error": ((523, 0.0, 90, 0.35, 4), (392, 0.1, 260, 0.35, 4)),
}


def tone_samples(freq, ms, vol, decay, attack=0.004):
    dur = ms / 1000.0
    n = int(RATE * (dur + 0.05))
    t = np.arange(n) / RATE
    end = dur * min(1.0, 6.0 / decay + 0.2)
    env = np.zeros(n)
    rise = t < attack
    env[rise] = vol * t[rise] / attack
    fall = (t >= attack) & (t < end)
    env[fall] = vol * (0.0001 / vol) ** ((t[fall] - attack) / max(end - attack, 1e-6))
    wave_ = 0.8 * np.sin(2 * math.pi * freq * t) + 0.2 * np.sin(2 * math.pi * freq * 2 * t)
    return env * wave_


def render(kind):
    notes = CUES[kind]
    total = max(at + ms / 1000.0 for _, at, ms, _, _ in notes) + 0.1
    buf = np.zeros(int(RATE * total) + RATE // 10)
    for freq, at, ms, vol, decay in notes:
        s = tone_samples(freq, ms, vol, decay)
        start = int(at * RATE)
        buf[start:start + len(s)] += s[:len(buf) - start]
    pcm = (np.clip(buf, -1.0, 1.0) * 32767).astype("<i2")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return out.getvalue()


_paths = {}


def cue_path(kind):
    path = _paths.get(kind)
    if path and os.path.exists(path):
        return path
    folder = os.path.join(tempfile.gettempdir(), "display_companion_cues")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, kind + ".wav")
    with open(path, "wb") as fh:
        fh.write(render(kind))
    _paths[kind] = path
    return path


def play(kind):
    if sys.platform != "win32" or kind not in CUES:
        return False
    try:
        import winsound
        winsound.PlaySound(cue_path(kind), winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    except Exception:
        return False
