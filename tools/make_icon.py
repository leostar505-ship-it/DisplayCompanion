import pathlib
import subprocess
import sys

from PIL import Image

root = pathlib.Path(__file__).resolve().parent.parent
svg = root / "assets" / "icon.svg"
png = root / "assets" / "icon.png"
ico = root / "assets" / "icon.ico"

subprocess.run(["rsvg-convert", "-w", "512", "-h", "512", str(svg), "-o", str(png)], check=True)
img = Image.open(png).convert("RGBA")
img.save(ico, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("wrote", png, ico, file=sys.stderr)
