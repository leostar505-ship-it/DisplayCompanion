import pathlib
import queue
import sys
import time
import tkinter as tk
import traceback
from tkinter import ttk

from PIL import Image, ImageTk

from . import __version__
from . import protocol as P
from .display import Display, H, W
from .link import SIMULATOR_NAME, SerialLink, SimLink, list_ports
from .modes import ALL_MODES
from .widgets import BG, LINE, MUTED, PANEL, TEXT, apply_style

ZOOM = 4


def asset_path(name):
    base = getattr(sys, "_MEIPASS", None)
    root = pathlib.Path(base) if base else pathlib.Path(__file__).resolve().parent.parent
    return root / "assets" / name


ROTATIONS = ("0\u00b0", "90\u00b0", "180\u00b0", "270\u00b0")


class App:
    def __init__(self, root):
        self.root = root
        self.display = Display()
        self.link = None
        self.replies = queue.Queue()
        self.last_tick = time.perf_counter()
        self.last_status = 0.0
        self.preview_version = -1
        self.current = None
        self.photo = None
        self.status_text = "Not connected"
        self.port_map = {}

        root.title("Display Companion %s" % __version__)
        root.configure(bg=BG)
        root.minsize(1100, 760)
        root.geometry("1220x800")
        apply_style(root)
        self._icon()
        self._build_topbar()
        self._build_body()
        self._build_statusbar()
        self.refresh_ports()
        self.select_mode(ALL_MODES[0].name)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def _icon(self):
        try:
            self.icon = tk.PhotoImage(file=str(asset_path("icon.png")))
            self.root.iconphoto(True, self.icon)
        except Exception:
            self.icon = None

    def _build_topbar(self):
        bar = ttk.Frame(self.root, padding=(12, 10))
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.port_var = tk.StringVar()
        ttk.Label(bar, text="Board").pack(side="left")
        self.port_box = ttk.Combobox(bar, textvariable=self.port_var, state="readonly", width=44)
        self.port_box.pack(side="left", padx=8)
        ttk.Button(bar, text="Refresh", command=self.refresh_ports).pack(side="left", padx=(0, 6))
        self.connect_btn = ttk.Button(bar, text="Connect", style="Accent.TButton", command=self.toggle_connect)
        self.connect_btn.pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="Test link", command=self.test_link).pack(side="left", padx=(0, 18))
        self.rotation_var = tk.StringVar(value=ROTATIONS[0])
        self.invert_var = tk.BooleanVar(value=False)
        self.swap_var = tk.BooleanVar(value=False)
        ttk.Label(bar, text="Rotation").pack(side="left")
        rot = ttk.Combobox(bar, textvariable=self.rotation_var, values=ROTATIONS, state="readonly", width=5)
        rot.pack(side="left", padx=(6, 12))
        rot.bind("<<ComboboxSelected>>", lambda e: self.apply_panel_options())
        for text, var in (("Invert colours", self.invert_var), ("Swap red/blue", self.swap_var)):
            ttk.Checkbutton(bar, text=text, variable=var, command=self.apply_panel_options).pack(side="left", padx=6)

    def _build_body(self):
        side = ttk.Frame(self.root, padding=(12, 4, 6, 12))
        side.grid(row=1, column=0, sticky="ns")
        ttk.Label(side, text="Mode", style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
        self.menu = tk.Listbox(side, height=len(ALL_MODES), exportselection=False, bg=PANEL, fg=TEXT,
                               selectbackground="#7a62ff", selectforeground="#ffffff", relief="flat",
                               highlightthickness=1, highlightbackground=LINE, activestyle="none",
                               font=("TkDefaultFont", 13), width=12)
        self.menu.pack(anchor="w")
        self.blurb = ttk.Label(side, text="", style="Muted.TLabel", wraplength=150, justify="left")
        self.blurb.pack(anchor="w", pady=10)
        self.modes = [cls(self) for cls in ALL_MODES]
        for mode in self.modes:
            self.menu.insert("end", mode.name)
        self.menu.bind("<<ListboxSelect>>", self._menu_selected)

        main = ttk.Frame(self.root, padding=(6, 4, 12, 12))
        main.grid(row=1, column=1, sticky="nsew")
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(1, weight=1)
        holder = tk.Frame(main, bg=BG, highlightthickness=2, highlightbackground=LINE)
        holder.pack(anchor="w")
        self.canvas = tk.Canvas(holder, width=W * ZOOM, height=H * ZOOM, bg="#000000", highlightthickness=0)
        self.canvas.pack()
        self.canvas_item = self.canvas.create_image(0, 0, anchor="nw")
        self.canvas.bind("<ButtonPress-1>", lambda e: self._mouse("press", e))
        self.canvas.bind("<B1-Motion>", lambda e: self._mouse("drag", e))
        self.canvas.bind("<ButtonRelease-1>", lambda e: self._mouse("release", e))
        ttk.Label(main, text="Live preview of the %dx%d screen" % (W, H), style="Muted.TLabel").pack(
            anchor="w", pady=(4, 10))
        self.panel = ttk.Frame(main)
        self.panel.pack(fill="x", anchor="nw")
        for mode in self.modes:
            mode.build(self.panel)

    def _build_statusbar(self):
        self.status = ttk.Label(self.root, text=self.status_text, style="Muted.TLabel", padding=(12, 4))
        self.status.grid(row=2, column=0, columnspan=2, sticky="ew")

    def _menu_selected(self, _event=None):
        sel = self.menu.curselection()
        if sel:
            self.select_mode(self.modes[sel[0]].name)

    def select_mode(self, name):
        target = next(m for m in self.modes if m.name == name)
        if self.current is target:
            return
        if self.current is not None:
            self.current.deactivate()
            self.current.frame.pack_forget()
        self.current = target
        target.frame.pack(fill="x", anchor="nw")
        self.menu.selection_clear(0, "end")
        self.menu.selection_set(self.modes.index(target))
        self.blurb.configure(text=target.blurb)
        target.activate()

    def set_cursor(self, name):
        self.canvas.configure(cursor=name)

    def _mouse(self, kind, event):
        if self.current is not None:
            self.current.mouse(kind, int(event.x // ZOOM), int(event.y // ZOOM))

    def refresh_ports(self):
        entries = [SIMULATOR_NAME]
        self.port_map = {SIMULATOR_NAME: None}
        for device, desc in list_ports():
            label = "%s - %s" % (device, desc) if desc else device
            entries.append(label)
            self.port_map[label] = device
        self.port_box.configure(values=entries)
        preferred = next((e for e in entries if "ESP32-S3" in e), None)
        keep = self.port_var.get()
        if keep not in entries:
            self.port_var.set(preferred or entries[-1] if len(entries) > 1 else entries[0])

    def toggle_connect(self):
        if self.link is not None:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        label = self.port_var.get()
        if not label:
            self.set_status("Pick a board first")
            return False
        device = self.port_map.get(label)
        link = SimLink() if device is None else SerialLink(device)
        link.on_reply = lambda text: self.replies.put(("reply", text))
        link.on_state = lambda text: self.replies.put(("state", text))
        if not link.open():
            self.set_status("Could not open %s: %s" % (label, link.error))
            return False
        self.link = link
        self.display.set_link(link)
        self.connect_btn.configure(text="Disconnect")
        self.apply_panel_options()
        self.display.hello()
        self.display.send_full()
        self.display.flush()
        self.set_status("Connected to %s" % label)
        self.current.on_link_change()
        return True

    def disconnect(self, message="Disconnected"):
        if self.link is not None:
            self.link.close()
        self.link = None
        self.display.set_link(None)
        self.connect_btn.configure(text="Connect")
        self.set_status(message)

    def apply_panel_options(self):
        self.display.set_rotation(ROTATIONS.index(self.rotation_var.get()))
        self.display.set_invert(self.invert_var.get())
        self.display.set_swap_rb(self.swap_var.get())

    def test_link(self):
        if self.link is None:
            self.set_status("Connect first, then test the link")
            return
        self.set_status("Hello sent, waiting for the board to answer...")
        self.display.hello()

    def send_raw(self, data):
        self.display.raw(data)

    def set_status(self, text):
        self.status_text = text
        self.status.configure(text=text)

    def drain(self):
        while True:
            try:
                kind, text = self.replies.get_nowait()
            except queue.Empty:
                return
            if kind == "reply":
                if text == "K":
                    self.display.ack()
                    continue
                for mode in self.modes:
                    mode.on_reply(text)
                if text.startswith(P.HELLO_REPLY_PREFIX):
                    self.set_status("Board answered: %s" % text)
            elif kind == "state":
                self.set_status(text)

    def check_link(self):
        if self.link is not None and not self.link.is_open:
            self.disconnect("Disconnected: %s" % (self.link.error or "link closed"))

    def update_preview(self):
        if self.display.version == self.preview_version:
            return
        self.preview_version = self.display.version
        img = self.display.rgb_image().resize((W * ZOOM, H * ZOOM), Image.NEAREST)
        self.photo = ImageTk.PhotoImage(img)
        self.canvas.itemconfigure(self.canvas_item, image=self.photo)

    def update_status(self, now):
        if now - self.last_status < 0.5:
            return
        self.last_status = now
        if self.link is not None:
            sent = self.link.bytes_sent
            text = "%s   |   sent %.1f KB   |   mode: %s" % (self.status_text.split("   |")[0], sent / 1024.0,
                                                          self.current.name)
            self.status.configure(text=text)

    def tick(self, dt=None):
        now = time.perf_counter()
        if dt is None:
            dt = min(0.25, now - self.last_tick)
        self.last_tick = now
        self.drain()
        self.check_link()
        if self.current is not None:
            self.current.tick(dt)
        self.update_preview()
        self.update_status(now)

    def _loop(self):
        try:
            self.tick()
        except Exception:
            traceback.print_exc()
        self.root.after(8, self._loop)

    def run(self):
        self._loop()
        self.root.mainloop()

    def close(self):
        try:
            if self.current is not None:
                self.current.deactivate()
            if self.link is not None:
                self.link.close()
        finally:
            self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    app.run()
