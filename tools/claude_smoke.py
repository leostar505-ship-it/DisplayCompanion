import os
import pathlib
import subprocess
import sys
import tempfile
import time
import tkinter as tk

root_dir = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from screenlink.assistant import api
from screenlink.assistant.settings import Settings
from screenlink.gui import App

out_dir = pathlib.Path(sys.argv[1])
out_dir.mkdir(parents=True, exist_ok=True)

root = tk.Tk()
app = App.__new__(App)
os.environ["APPDATA"] = tempfile.mkdtemp()
app.assistant_settings = Settings(pathlib.Path(tempfile.mkdtemp()) / "a.json")
app.assistant_settings.set("auto_download", False)
App.__init__(app, root)
root.geometry("+0+0")


def pump(seconds, step=0.016):
    end = time.time() + seconds
    while time.time() < end:
        app.tick(step)
        root.update_idletasks()
        root.update()
        time.sleep(step)


def shot(name):
    pump(0.05)
    subprocess.run(["import", "-window", "root", str(out_dir / (name + ".png"))], check=True)
    app.display.rgb_image().resize((640, 480)).save(out_dir / (name + "_screen.png"))


app.port_var.set("Simulator (no board)")
assert app.connect()
app.select_mode("Claude")
mode = app.current
assert mode.name == "Claude"
pump(0.3)
s = mode.settings
s.set("api_key", "sk-test")
s.set("backend", "api")
s.set("hud_speed", 2.5)
s.set("typing_cps", 90)
s.set("hotkey", "ctrl+alt+c")
mode.cps.set(90)
cues_played = []
mode.play = cues_played.append
mode.grab = lambda: "AAAA"
calls = []


def fake_ask(key, model, question, image, limit, history=(), **kw):
    calls.append((key, model, question, image, limit, list(history)))
    time.sleep(0.3)
    return "Your screen shows a code editor. It looks like Python, and the tests are passing. Nice work!"


mode.ask = fake_ask
shot("claude_idle")
before = mode.limit()
mode.size.set(16)
mode._font_changed()
assert mode.limit() < before, (mode.limit(), before)
mode.size.set(11)
mode._font_changed()

mode.ask_var.set("What is on my screen?")
mode._ask_typed()
assert mode.phase == "shot", mode.phase
pump(0.9)
shot("claude_hud_screenshot")
deadline = time.time() + 15
phases = []
while time.time() < deadline and mode.phase != "idle":
    pump(0.05)
    if not phases or phases[-1] != mode.phase:
        phases.append(mode.phase)
    if mode.phase == "typing" and len(phases) and phases.count("typing") == 1:
        pump(0.25)
        shot("claude_typing")
        phases.append("typing-shot")
assert mode.phase == "idle", mode.phase
print("phases:", phases)
print("cues:", cues_played)
assert cues_played[:4] == ["screenshot", "thinking", "responding", "done"] or cues_played[:3] == [
    "screenshot", "responding", "done"], cues_played
assert calls and calls[0][2] == "What is on my screen?" and calls[0][3] == "AAAA"
assert mode.reply_text.startswith("Your screen shows")
pump(0.3)
shot("claude_done")
assert mode.hud.current_kind() == "done", mode.hud.current_kind()

mode.ask = lambda *a, **k: (_ for _ in ()).throw(api.AssistantError("The API key was rejected."))
cues_played.clear()
mode.ask_var.set("again")
mode._ask_typed()
deadline = time.time() + 15
while time.time() < deadline and "error" not in cues_played:
    pump(0.05)
assert cues_played[-1] == "error", cues_played
assert mode.phase == "idle"
pump(0.3)
shot("claude_error")

s.set("api_key", "")
mode.settings.data["api_key"] = ""
mode.settings.set("backend", "api")
import os
os.environ.pop("ANTHROPIC_API_KEY", None)
cues_played.clear()
mode.ask_var.set("no key")
mode._ask_typed()
pump(0.2)
assert cues_played == ["error"], cues_played

mode.listen_now()
pump(0.1)
assert mode.phase == "idle"
assert "voice model" in mode.status.cget("text").lower(), mode.status.cget("text")

app.select_mode("Text")
assert not mode.active
print("ALL OK")
root.destroy()
