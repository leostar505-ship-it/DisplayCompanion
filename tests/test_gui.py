import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_gui_smoke_all_modes(tmp_path):
    try:
        import tkinter
    except ImportError:
        pytest.skip("tkinter not available")
    xvfb = shutil.which("xvfb-run")
    if xvfb is None or shutil.which("import") is None:
        pytest.skip("xvfb-run / ImageMagick not available")
    res = subprocess.run(
        [xvfb, "-a", "-s", "-screen 0 1280x800x24", sys.executable, str(ROOT / "tools" / "gui_smoke.py"),
         str(tmp_path)],
        capture_output=True, text=True, timeout=240,
    )
    assert "ALL OK" in res.stdout, res.stdout + res.stderr


def test_claude_mode_flow(tmp_path):
    try:
        import tkinter
    except ImportError:
        pytest.skip("tkinter not available")
    xvfb = shutil.which("xvfb-run")
    if xvfb is None or shutil.which("import") is None:
        pytest.skip("xvfb-run / ImageMagick not available")
    res = subprocess.run(
        [xvfb, "-a", "-s", "-screen 0 1280x800x24", sys.executable, str(ROOT / "tools" / "claude_smoke.py"),
         str(tmp_path)],
        capture_output=True, text=True, timeout=240,
    )
    assert "ALL OK" in res.stdout, res.stdout + res.stderr
