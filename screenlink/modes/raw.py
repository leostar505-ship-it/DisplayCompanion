import re
import time
import tkinter as tk
from tkinter import ttk

from .. import protocol as P
from ..display import H, W
from ..widgets import FIELD, MUTED, TEXT
from .base import Mode

KIND_HEX = "hex"
KIND_TEXT = "text"
KIND_FRAME = "frame"


def parse_hex(text):
    cleaned = re.sub(r"0x", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", cleaned)
    if not cleaned and text.strip():
        raise ValueError("no hex digits found")
    if len(cleaned) % 2:
        raise ValueError("odd number of hex digits")
    return bytes.fromhex(cleaned)


def preview_hex(data, limit=24):
    head = " ".join("%02x" % b for b in data[:limit])
    return head + (" ..." if len(data) > limit else "")


class RawMode(Mode):
    name = "Raw"
    blurb = "Send exact bytes, build protocol frames, see replies"

    def __init__(self, app):
        super().__init__(app)

    def build(self, parent):
        f = ttk.Frame(parent)
        self.frame = f
        self.kind_var = tk.StringVar(value=KIND_FRAME)
        self.cmd_var = tk.StringVar(value="CLEAR")
        self.newline_var = tk.BooleanVar(value=True)

        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky="n", padx=(0, 24))
        row = ttk.Frame(left)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Send as", width=8).pack(side="left")
        for label, value in (("Protocol frame", KIND_FRAME), ("Hex bytes", KIND_HEX), ("Text", KIND_TEXT)):
            ttk.Radiobutton(row, text=label, value=value, variable=self.kind_var, command=self._kind_changed).pack(
                side="left", padx=4)
        self.frame_row = ttk.Frame(left)
        self.frame_row.pack(anchor="w", pady=2)
        ttk.Label(self.frame_row, text="Command", width=8).pack(side="left")
        names = list(P.COMMAND_NAMES) + ["custom (hex byte below)"]
        ttk.Combobox(self.frame_row, textvariable=self.cmd_var, values=names, width=24).pack(side="left")
        self.payload_label = ttk.Label(left, text="Payload / data", style="Muted.TLabel")
        self.payload_label.pack(anchor="w")
        self.input = tk.Text(left, width=52, height=4, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat",
                             font=("Courier", 10))
        self.input.pack(anchor="w", pady=3)
        self.input.insert("1.0", "ff 00 00")
        self.input.bind("<Control-Return>", lambda e: self.send() or "break")
        self.newline_check = ttk.Checkbutton(left, text="Add newline (Text only)", variable=self.newline_var)
        self.newline_check.pack(anchor="w")
        row = ttk.Frame(left)
        row.pack(anchor="w", pady=4)
        ttk.Button(row, text="Send  (Ctrl+Enter)", style="Accent.TButton", command=self.send).pack(side="left")
        ttk.Button(row, text="Hello / ping", command=self.hello).pack(side="left", padx=6)

        quick = ttk.Frame(f)
        quick.grid(row=0, column=1, sticky="n", padx=(0, 24))
        ttk.Label(quick, text="Quick commands", style="Muted.TLabel").pack(anchor="w")
        grid = ttk.Frame(quick)
        grid.pack(anchor="w")
        buttons = (
            ("Red", lambda: self.fill((255, 0, 0))), ("Green", lambda: self.fill((0, 255, 0))),
            ("Blue", lambda: self.fill((0, 0, 255))), ("White", lambda: self.fill((255, 255, 255))),
            ("Black", lambda: self.fill((0, 0, 0))), ("Test pattern", self.pattern),
        )
        for i, (label, cmd) in enumerate(buttons):
            ttk.Button(grid, text=label, command=cmd, width=12).grid(row=i // 2, column=i % 2, padx=2, pady=2)

        logf = ttk.Frame(f)
        logf.grid(row=0, column=2, sticky="n")
        ttk.Label(logf, text="Log", style="Muted.TLabel").pack(anchor="w")
        self.log = tk.Text(logf, width=46, height=9, bg=FIELD, fg=TEXT, relief="flat", state="disabled",
                           font=("Courier", 9))
        self.log.pack(anchor="w")
        self.log.tag_configure("out", foreground="#8fb8ff")
        self.log.tag_configure("in", foreground="#8fffa8")
        self.log.tag_configure("err", foreground="#ff8f8f")
        self._kind_changed()
        return f

    def _kind_changed(self):
        kind = self.kind_var.get()
        if kind == KIND_FRAME:
            self.frame_row.pack(anchor="w", pady=2, before=self.payload_label)
        else:
            self.frame_row.pack_forget()

    def _log(self, text, tag="out"):
        stamp = time.strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", "%s  %s\n" % (stamp, text), tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def on_reply(self, text):
        self._log("<- " + text, "in")

    def _command_code(self):
        raw = self.cmd_var.get().strip()
        if raw.upper() in P.COMMAND_NAMES:
            return P.COMMAND_NAMES[raw.upper()]
        try:
            return int(raw, 0) & 0xFF
        except ValueError:
            pass
        return None

    def send(self):
        body = self.input.get("1.0", "end-1c")
        kind = self.kind_var.get()
        try:
            if kind == KIND_TEXT:
                data = body.encode("utf-8")
                if self.newline_var.get():
                    data += b"\n"
            elif kind == KIND_HEX:
                data = parse_hex(body)
            else:
                code = self._command_code()
                if code is None:
                    raise ValueError("unknown command name or number")
                data = P.frame(code, parse_hex(body) if body.strip() else b"")
        except ValueError as exc:
            self._log("error: %s" % exc, "err")
            return
        if not data:
            self._log("nothing to send", "err")
            return
        self.app.send_raw(data)
        self._log("-> %d bytes: %s" % (len(data), preview_hex(data)), "out")

    def hello(self):
        self.app.send_raw(P.hello())
        self._log("-> HELLO", "out")

    def fill(self, rgb):
        self.display.clear(rgb)
        self.display.flush()
        self._log("-> clear screen %s" % (rgb,), "out")

    def pattern(self):
        d = self.display
        d.clear((0, 0, 0))
        bars = [(255, 0, 0), (255, 127, 0), (255, 255, 0), (0, 255, 0), (0, 255, 255), (0, 0, 255), (160, 0, 255),
                (255, 255, 255)]
        bw = W // len(bars)
        d.rects([(i * bw, 0, bw, H - 20, c) for i, c in enumerate(bars)])
        grey = [(i * (W // 16), H - 20, W // 16, 20, (i * 17, i * 17, i * 17)) for i in range(16)]
        d.rects(grey)
        d.lines([(0, 0, W - 1, 0, (255, 255, 255)), (0, H - 1, W - 1, H - 1, (255, 255, 255)),
                 (0, 0, 0, H - 1, (255, 255, 255)), (W - 1, 0, W - 1, H - 1, (255, 255, 255)),
                 (0, 0, W - 1, H - 1, (0, 0, 0)), (W - 1, 0, 0, H - 1, (0, 0, 0))])
        d.flush()
        self._log("-> test pattern", "out")
