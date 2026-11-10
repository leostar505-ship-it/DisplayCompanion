import json
import os
import pathlib

DEFAULTS = {
    "backend": "claude_code",
    "api_key": "",
    "model": "claude-sonnet-5-5",
    "hotkey": "ctrl+alt+c",
    "wake_word": True,
    "screenshot_mode": "auto",
    "sounds": True,
    "web_search": True,
    "hud": True,
    "spinner": True,
    "hud_scale": 1.5,
    "hud_speed": 1.6,
    "font": "",
    "font_size": 11,
    "typing_cps": 32,
    "voice_engine": "auto",
    "dictation_model": "large-v3-q5_0",
    "wake_model": "small.en",
    "use_gpu": True,
    "auto_download": True,
}


def config_dir():
    base = os.environ.get("APPDATA")
    root = pathlib.Path(base) if base else pathlib.Path.home() / ".config"
    return root / "DisplayCompanion"


class Settings:
    def __init__(self, path=None):
        self.path = pathlib.Path(path) if path else config_dir() / "assistant.json"
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(raw, dict):
            if "screenshot_mode" not in raw and raw.get("screenshot") is False:
                raw["screenshot_mode"] = "never"
            for key in DEFAULTS:
                if key in raw and type(raw[key]) is type(DEFAULTS[key]):
                    self.data[key] = raw[key]
                elif key in raw and isinstance(DEFAULTS[key], float) and isinstance(raw[key], int):
                    self.data[key] = float(raw[key])

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
            return True
        except OSError:
            return False

    def get(self, key):
        return self.data[key]

    def set(self, key, value):
        if key in DEFAULTS:
            self.data[key] = value

    def api_key(self):
        return self.data["api_key"].strip() or os.environ.get("ANTHROPIC_API_KEY", "").strip()
