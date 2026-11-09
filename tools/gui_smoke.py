import pathlib
import subprocess
import sys
import tkinter as tk

root_dir = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from screenlink.gui import App, ZOOM
from screenlink.protocol import HEIGHT, WIDTH

out_dir = pathlib.Path(sys.argv[1])
out_dir.mkdir(parents=True, exist_ok=True)

root = tk.Tk()
app = App(root)
root.geometry("+0+0")


def pump(n=8, dt=0.05):
    for _ in range(n):
        app.tick(dt)
        root.update_idletasks()
        root.update()


def shot(name):
    pump(2)
    path = out_dir / (name + ".png")
    subprocess.run(["import", "-window", "root", str(path)], check=True)
    crop = app.display.rgb_image()
    crop.resize((WIDTH * 4, HEIGHT * 4)).save(out_dir / (name + "_screen.png"))


app.port_var.set("Simulator (no board)")
assert app.connect()
pump(4)
print("connected:", app.status_text)

app.select_mode("Visualiser")
pump(60, 0.03)
shot("visualiser_radial_wave")
vis = app.current
for label, name in (("Radial spectrum + bass ring", "radial"), ("Waveform only", "wave"), ("Mirrored peak-hold bars", "bars")):
    vis.visual_var.set(label)
    vis._on_visual()
    pump(40, 0.03)
    shot("visualiser_" + name)
vis.infinite_var.set(True)
vis._on_hold()
pump(40, 0.03)
shot("visualiser_hold")
vis.visual_var.set("Radial spectrum + bass ring + waveform")
vis._on_visual()
vis.mode_var.set("Loudness gradient: pink to red")
vis._on_mode()
pump(20, 0.03)
shot("visualiser_loudness")

app.select_mode("Draw")
draw = app.current
draw.color.set((255, 45, 85))
draw.tool_var.set("Pen")
draw.brush.set(3)
for kind, x, y in [("press", 10, 10), ("drag", 40, 50), ("drag", 80, 20), ("release", 80, 20)]:
    draw.mouse(kind, x, y)
draw.tool_var.set("Filled ellipse")
draw.color.set((0, 200, 255))
for kind, x, y in [("press", 100, 15), ("drag", 130, 40), ("drag", 150, 70), ("release", 150, 70)]:
    draw.mouse(kind, x, y)
draw.tool_var.set("Rectangle")
draw.color.set((255, 255, 0))
for kind, x, y in [("press", 5, 55), ("drag", 60, 75), ("release", 60, 75)]:
    draw.mouse(kind, x, y)
draw.tool_var.set("Fill")
draw.color.set((40, 160, 40))
draw.mouse("press", 30, 60)
draw.mouse("release", 30, 60)
pump(4)
shot("draw")
board = app.link.board
assert (board.presented == app.display.canvas.buf).all(), "board and preview disagree"
before = app.display.snapshot().copy()
draw.do_undo()
pump(2)
assert not (app.display.canvas.buf == before).all()
assert (app.link.board.presented == app.display.canvas.buf).all()
draw.do_redo()
pump(2)
assert (app.display.canvas.buf == before).all()

app.select_mode("Text")
txt = app.current
txt.box.delete("1.0", "end")
txt.box.insert("1.0", "ScreenLink\nworks!")
txt._mark()
pump(10, 0.05)
shot("text_static")
rgb = app.display.canvas.to_rgb()
assert (rgb.sum(axis=2) > 600).sum() > 80, "text did not render"
assert ((rgb[..., 0] > 200) & (rgb[..., 1] < 100)).sum() < 10, "draw artwork leaked into text mode"
txt.scroll_var.set(True)
txt.box.delete("1.0", "end")
txt.box.insert("1.0", "Scrolling message across the little screen")
txt._mark()
pump(30, 0.05)
shot("text_scroll")
txt.scroll_var.set(False)
txt.auto_var.set(True)
txt._mark()
pump(10, 0.05)
shot("text_autofit")

drawn = before.copy()
app.select_mode("Draw")
pump(2)
assert (app.display.canvas.buf == drawn).all(), "draw canvas not restored"
assert (app.link.board.presented == drawn).all(), "board did not get restored canvas"
app.select_mode("Text")
pump(10, 0.05)

app.select_mode("Image")
img = app.current
from PIL import Image, ImageDraw

test = Image.new("RGB", (400, 400), (20, 20, 60))
d = ImageDraw.Draw(test)
for i in range(0, 190, 40):
    d.ellipse([i, i, 400 - i, 400 - i], outline=(255, 100 + i // 3, 50), width=6)
test_path = out_dir / "test_image.png"
test.save(test_path)
assert img.load(str(test_path))
pump(6)
shot("image")
frames = []
for k in range(6):
    f = Image.new("RGB", (64, 32), (0, 0, 0))
    ImageDraw.Draw(f).rectangle([k * 10, 4, k * 10 + 12, 28], fill=(255, 0, 255))
    frames.append(f)
gif_path = out_dir / "anim.gif"
frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=60, loop=0)
assert img.load(str(gif_path))
seen = set()
for _ in range(60):
    pump(1, 0.03)
    seen.add(app.display.canvas.buf.tobytes())
assert len(seen) >= 4, len(seen)
print("gif frames seen:", len(seen))

app.select_mode("Terminal")
term = app.current
for line in ["hello world", "this is the terminal mode", "each line scrolls up", "and wraps long lines automatically"]:
    term.entry_var.set(line)
    term.submit()
pump(4)
shot("terminal")

app.select_mode("Raw")
raw = app.current
raw.kind_var.set("frame")
raw._kind_changed()
raw.cmd_var.set("CLEAR")
raw.input.delete("1.0", "end")
raw.input.insert("1.0", "e0 07")
raw.send()
pump(4)
assert app.display.canvas.buf[10, 10] == 0x07E0, hex(app.display.canvas.buf[10, 10])
raw.kind_var.set("hex")
raw._kind_changed()
raw.input.delete("1.0", "end")
raw.input.insert("1.0", "zz")
raw.send()
raw.input.delete("1.0", "end")
raw.input.insert("1.0", "a5 5a 03 07 00 01 05 05 14 14 00 f8")
raw.send()
raw.hello()
pump(6)
raw.pattern()
pump(4)
shot("raw")
print("log:", raw.log.get("1.0", "end").strip().splitlines()[-4:])

app.rotation_var.set("180\u00b0")
app.swap_var.set(True)
app.apply_panel_options()
pump(2)
assert app.link.board.rotation == 2 and app.link.board.swap_rb
app.disconnect()
pump(2)
assert app.link is None
print("ALL OK")
app.close()
