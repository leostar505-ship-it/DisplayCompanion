import tkinter as tk
from tkinter import filedialog, ttk

import numpy as np
from PIL import Image, ImageDraw

from .. import colors
from ..canvas import bresenham
from ..display import H, W, to565
from ..widgets import ColorField, Slider
from .base import Mode

TOOLS = ("Pen", "Eraser", "Line", "Rectangle", "Filled rectangle", "Ellipse", "Filled ellipse", "Fill", "Pick colour")
SHAPES = ("Line", "Rectangle", "Filled rectangle", "Ellipse", "Filled ellipse")
PALETTE = (
    "#000000", "#ffffff", "#ff0000", "#ff7f00", "#ffff00", "#7fff00", "#00ff00", "#00ff7f",
    "#00ffff", "#007fff", "#0000ff", "#7f00ff", "#ff00ff", "#ff007f", "#808080", "#5c3a21",
)
UNDO_LIMIT = 40


def flood_spans(buf, x, y, new565):
    old = int(buf[y, x])
    if old == new565:
        return []
    work = buf.copy()
    spans = []
    stack = [(x, y)]
    while stack:
        sx, sy = stack.pop()
        if int(work[sy, sx]) != old:
            continue
        lx = sx
        while lx > 0 and int(work[sy, lx - 1]) == old:
            lx -= 1
        rx = sx
        while rx < W - 1 and int(work[sy, rx + 1]) == old:
            rx += 1
        work[sy, lx:rx + 1] = new565
        spans.append((lx, sy, rx - lx + 1, 1))
        for ny in (sy - 1, sy + 1):
            if 0 <= ny < H:
                xx = lx
                while xx <= rx:
                    if int(work[ny, xx]) == old:
                        stack.append((xx, ny))
                        while xx <= rx and int(work[ny, xx]) == old:
                            xx += 1
                    else:
                        xx += 1
    return spans


def shape_points(tool, a, b):
    x0, y0 = a
    x1, y1 = b
    if tool == "Line":
        return bresenham(x0, y0, x1, y1)
    lx, hx = min(x0, x1), max(x0, x1)
    ly, hy = min(y0, y1), max(y0, y1)
    if tool in ("Rectangle", "Filled rectangle"):
        if tool == "Filled rectangle":
            return [(x, y) for y in range(ly, hy + 1) for x in range(lx, hx + 1)]
        pts = []
        pts += bresenham(lx, ly, hx, ly)
        pts += bresenham(lx, hy, hx, hy)
        pts += bresenham(lx, ly, lx, hy)
        pts += bresenham(hx, ly, hx, hy)
        return pts
    mask = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(mask)
    if tool == "Filled ellipse":
        draw.ellipse([lx, ly, hx, hy], fill=255)
    else:
        draw.ellipse([lx, ly, hx, hy], outline=255)
    ys, xs = np.nonzero(np.array(mask))
    return list(zip(xs.tolist(), ys.tolist()))


class DrawMode(Mode):
    name = "Draw"
    blurb = "Draw on the screen with the mouse"

    def __init__(self, app):
        super().__init__(app)
        self.undo = []
        self.redo = []
        self.start = None
        self.last = None
        self.base = None
        self.active_tool = None
        self.saved = None

    def build(self, parent):
        f = ttk.Frame(parent)
        self.frame = f
        self.tool_var = tk.StringVar(value="Pen")

        tools = ttk.Frame(f)
        tools.grid(row=0, column=0, sticky="n", padx=(0, 24))
        ttk.Label(tools, text="Tool", style="Muted.TLabel").pack(anchor="w")
        grid = ttk.Frame(tools)
        grid.pack(anchor="w")
        for i, name in enumerate(TOOLS):
            ttk.Radiobutton(grid, text=name, value=name, variable=self.tool_var).grid(
                row=i % 5, column=i // 5, sticky="w", padx=(0, 14), pady=1)

        paint = ttk.Frame(f)
        paint.grid(row=0, column=1, sticky="n", padx=(0, 24))
        self.color = ColorField(paint, "Colour", "#ff2d55")
        self.color.pack(anchor="w", pady=2)
        sw = ttk.Frame(paint)
        sw.pack(anchor="w", pady=4)
        for i, hexv in enumerate(PALETTE):
            tk.Button(sw, bg=hexv, activebackground=hexv, width=2, height=1, relief="flat", bd=1,
                      highlightthickness=0, command=lambda h=hexv: self.color.set(colors.parse_hex(h))).grid(
                row=i // 8, column=i % 8, padx=1, pady=1)
        self.brush = Slider(paint, "Brush size", 1, 10, 1, integer=True)
        self.brush.pack(anchor="w", pady=2)

        actions = ttk.Frame(f)
        actions.grid(row=0, column=2, sticky="n")
        row1 = ttk.Frame(actions)
        row1.pack(anchor="w", pady=2)
        ttk.Button(row1, text="Undo", command=self.do_undo).pack(side="left", padx=(0, 6))
        ttk.Button(row1, text="Redo", command=self.do_redo).pack(side="left", padx=(0, 6))
        ttk.Button(row1, text="Clear", command=self.clear_all).pack(side="left")
        row2 = ttk.Frame(actions)
        row2.pack(anchor="w", pady=2)
        ttk.Button(row2, text="Fill screen with colour", command=self.fill_all).pack(side="left", padx=(0, 6))
        row3 = ttk.Frame(actions)
        row3.pack(anchor="w", pady=2)
        ttk.Button(row3, text="Resend to board", command=self.resend).pack(side="left", padx=(0, 6))
        ttk.Button(row3, text="Save PNG...", command=self.save_png).pack(side="left")
        ttk.Label(actions, text="Click and drag on the preview above.\nShapes preview while you drag.",
                  style="Muted.TLabel", justify="left").pack(anchor="w", pady=8)
        return f

    def activate(self):
        self.app.set_cursor("crosshair")
        if self.saved is None:
            self.display.clear((0, 0, 0))
        else:
            self.display.restore(self.saved)
            self.display.send_full()
        self.display.flush()

    def deactivate(self):
        self.saved = self.display.snapshot()
        self.app.set_cursor("")

    def _push_undo(self):
        self.undo.append(self.display.snapshot())
        if len(self.undo) > UNDO_LIMIT:
            self.undo.pop(0)
        self.redo.clear()

    def _stamp(self, points, rgb):
        size = self.brush.get()
        off = size // 2
        rects = [(px - off, py - off, size, size, rgb) for px, py in points]
        self.display.rects(rects)

    def _current(self, tool):
        return (0, 0, 0) if tool == "Eraser" else self.color.get()

    def mouse(self, kind, x, y):
        x = min(W - 1, max(0, x))
        y = min(H - 1, max(0, y))
        if kind == "press":
            tool = self.tool_var.get()
            self.active_tool = tool
            self.start = (x, y)
            self.last = (x, y)
            if tool == "Pick colour":
                rgb = self.display.canvas.to_rgb()[y, x]
                self.color.set(tuple(int(v) for v in rgb))
                return
            self._push_undo()
            self.base = self.display.snapshot()
            if tool in ("Pen", "Eraser"):
                self._stamp([(x, y)], self._current(tool))
                self.display.flush()
            elif tool == "Fill":
                spans = flood_spans(self.display.canvas.buf, x, y, to565(self.color.get()))
                col = self.color.get()
                self.display.rects([(sx, sy, sw, sh, col) for sx, sy, sw, sh in spans])
                self.display.flush()
        elif kind == "drag":
            tool = self.active_tool
            if tool in ("Pen", "Eraser") and self.last is not None:
                pts = bresenham(self.last[0], self.last[1], x, y)
                self._stamp(pts, self._current(tool))
                self.last = (x, y)
                self.display.flush()
            elif tool in SHAPES and self.start is not None:
                self.display.restore(self.base)
                with self.display.silent():
                    self._stamp(shape_points(tool, self.start, (x, y)), self.color.get())
        elif kind == "release":
            tool = self.active_tool
            if tool in SHAPES and self.start is not None and self.base is not None:
                self.display.restore(self.base)
                self._stamp(shape_points(tool, self.start, (x, y)), self.color.get())
                self.display.flush()
            self.start = None
            self.last = None
            self.active_tool = None

    def do_undo(self):
        if not self.undo:
            return
        self.redo.append(self.display.snapshot())
        self.display.restore(self.undo.pop())
        self.resend()

    def do_redo(self):
        if not self.redo:
            return
        self.undo.append(self.display.snapshot())
        self.display.restore(self.redo.pop())
        self.resend()

    def clear_all(self):
        self._push_undo()
        self.display.clear((0, 0, 0))
        self.display.flush()

    def fill_all(self):
        self._push_undo()
        self.display.clear(self.color.get())
        self.display.flush()

    def resend(self):
        self.display.send_full()
        self.display.flush()

    def save_png(self):
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG image", "*.png")])
        if path:
            self.display.rgb_image().save(path)
