import collections
import threading
import time

from . import protocol as P
from .simboard import SimBoard

SIMULATOR_NAME = "Simulator (no board)"
KEEPALIVE_S = 1.0


def list_ports():
    found = []
    try:
        from serial.tools import list_ports as lp
    except Exception:
        return found
    for info in lp.comports():
        desc = info.description or ""
        if getattr(info, "vid", None) == 0x303A:
            desc = (desc + " [ESP32-S3]").strip()
        found.append((info.device, desc))
    return found


class Link:
    def __init__(self):
        self.on_reply = None
        self.on_state = None
        self.bytes_sent = 0
        self.error = ""
        self.is_open = False

    def open(self):
        return False

    def close(self):
        self.is_open = False

    def send(self, data):
        pass

    def send_latest(self, data):
        self.send(data)

    def _reply(self, text):
        if self.on_reply:
            self.on_reply(text)

    def _state(self, text):
        if self.on_state:
            self.on_state(text)


class SimLink(Link):
    def __init__(self):
        super().__init__()
        self.board = SimBoard()

    def open(self):
        self.is_open = True
        return True

    def send(self, data):
        if not self.is_open:
            return
        self.bytes_sent += len(data)
        self.board.feed(data)
        self.board.flush()
        raw = self.board.take_replies()
        if raw:
            for line in raw.decode("ascii", "replace").splitlines():
                self._reply(line)


class SerialLink(Link):
    def __init__(self, port, baud=P.BAUD):
        super().__init__()
        self.port = port
        self.baud = baud
        self.ser = None
        self._cv = threading.Condition()
        self._queue = collections.deque()
        self._latest = None
        self._stop = False
        self._threads = []
        self._last_write = time.perf_counter()

    def open(self):
        try:
            import serial
            self.ser = serial.Serial()
            self.ser.port = self.port
            self.ser.baudrate = self.baud
            self.ser.timeout = 0.05
            self.ser.write_timeout = 2.0
            self.ser.dtr = False
            self.ser.rts = False
            self.ser.open()
        except Exception as exc:
            self.error = str(exc)
            self.is_open = False
            return False
        self._stop = False
        self._last_write = time.perf_counter()
        self.is_open = True
        self._threads = [
            threading.Thread(target=self._write_loop, daemon=True),
            threading.Thread(target=self._read_loop, daemon=True),
        ]
        for t in self._threads:
            t.start()
        return True

    def close(self):
        with self._cv:
            self._stop = True
            self._cv.notify_all()
        for t in self._threads:
            t.join(timeout=1.5)
        self._threads = []
        try:
            if self.ser is not None:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.is_open = False

    def send(self, data):
        if not self.is_open:
            return
        with self._cv:
            self._queue.append(bytes(data))
            self._cv.notify()

    def send_latest(self, data):
        if not self.is_open:
            return
        with self._cv:
            self._latest = bytes(data)
            self._cv.notify()

    def _fail(self, exc):
        self.error = str(exc)
        self.is_open = False
        self._state("disconnected: %s" % exc)

    def _write_loop(self):
        while True:
            with self._cv:
                while not self._stop and not self._queue and self._latest is None:
                    if time.perf_counter() - self._last_write >= KEEPALIVE_S:
                        break
                    self._cv.wait(0.2)
                if self._stop:
                    return
                if self._queue:
                    data = self._queue.popleft()
                elif self._latest is not None:
                    data = self._latest
                    self._latest = None
                else:
                    data = P.heartbeat()
            try:
                if len(data) > 8192:
                    for i in range(0, len(data), 4096):
                        self.ser.write(data[i:i + 4096])
                        time.sleep(0.001)
                else:
                    self.ser.write(data)
                self._last_write = time.perf_counter()
                self.bytes_sent += len(data)
            except Exception as exc:
                self._fail(exc)
                return

    def _read_loop(self):
        pending = bytearray()
        while not self._stop:
            try:
                chunk = self.ser.read(256)
            except Exception as exc:
                if not self._stop:
                    self._fail(exc)
                return
            if not chunk:
                continue
            pending += chunk
            while b"\n" in pending:
                line, _, rest = bytes(pending).partition(b"\n")
                pending = bytearray(rest)
                text = line.decode("ascii", "replace").strip()
                if text:
                    self._reply(text)
            if len(pending) > 4096:
                pending.clear()
