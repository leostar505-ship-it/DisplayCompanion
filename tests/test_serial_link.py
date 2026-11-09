import os
import sys
import time

import pytest

from screenlink import protocol as P
from screenlink.display import Display
from screenlink.link import SerialLink

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="needs a pty")


def wait_for(predicate, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def pty_pair():
    master, slave = os.openpty()
    yield master, os.ttyname(slave)
    os.close(master)
    os.close(slave)


def read_available(fd, want, timeout=3.0):
    got = bytearray()
    end = time.time() + timeout
    while time.time() < end and len(got) < want:
        try:
            got += os.read(fd, 65536)
        except BlockingIOError:
            time.sleep(0.005)
    return bytes(got)


def test_frames_reach_the_port_intact(pty_pair):
    master, name = pty_pair
    os.set_blocking(master, False)
    link = SerialLink(name)
    assert link.open(), link.error
    try:
        disp = Display()
        disp.set_link(link)
        disp.clear((0, 0, 0))
        disp.rects([(1, 2, 30, 20, (255, 0, 0))])
        disp.flush()
        expected = P.clear(0) + P.rects([(1, 2, 30, 20, P.rgb565(255, 0, 0))]) + P.present()
        got = read_available(master, len(expected))
        assert got == expected
    finally:
        link.close()


def test_large_image_survives(pty_pair):
    master, name = pty_pair
    os.set_blocking(master, False)
    link = SerialLink(name)
    assert link.open(), link.error
    try:
        disp = Display()
        disp.set_link(link)
        disp.rects([(0, 0, 160, 80, (10, 200, 30))])
        disp.send_full()
        disp.flush()
        got = read_available(master, 26000)
        dec = P.Decoder()
        cmds = [c for c, _ in dec.feed(got)]
        assert P.CMD_RECTS in cmds and P.CMD_IMAGE in cmds and P.CMD_PRESENT in cmds
    finally:
        link.close()


def test_board_reply_reaches_callback(pty_pair):
    master, name = pty_pair
    link = SerialLink(name)
    replies = []
    link.on_reply = replies.append
    assert link.open(), link.error
    try:
        os.write(master, b"SCREENLINK 1 160x80\n")
        assert wait_for(lambda: replies)
        assert replies[0] == "SCREENLINK 1 160x80"
    finally:
        link.close()


def test_latest_frame_replaces_stale_one(pty_pair):
    master, name = pty_pair
    os.set_blocking(master, False)
    link = SerialLink(name)
    assert link.open(), link.error
    try:
        for i in range(200):
            link.send_latest(P.clear(i))
        time.sleep(0.4)
        got = read_available(master, 7, timeout=1.0)
        dec = P.Decoder()
        cmds = dec.feed(got)
        assert cmds
    finally:
        link.close()


def test_open_failure_is_reported():
    link = SerialLink("/dev/does-not-exist")
    assert not link.open()
    assert link.error
