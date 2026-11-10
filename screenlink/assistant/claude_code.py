import base64
import os
import shutil
import subprocess
import sys
import tempfile

from .api import SUFFIX, MAX_HISTORY, AssistantError, clean_reply

TIMEOUT = 150


def find():
    found = shutil.which("claude")
    if found:
        return found
    home = os.path.expanduser("~")
    for rel in (os.path.join(".local", "bin", "claude.exe"), os.path.join(".local", "bin", "claude"),
                os.path.join("AppData", "Roaming", "npm", "claude.cmd")):
        path = os.path.join(home, rel)
        if os.path.isfile(path):
            return path
    return None


def alias(model):
    name = (model or "").lower()
    for key in ("haiku", "sonnet", "opus"):
        if key in name:
            return key
    return model or "sonnet"


def build_prompt(question, limit, history, has_image):
    parts = [
        "You are Claude, answering through Display Companion, a tiny text screen on the user's desk. "
        "Your whole reply must be at most %d characters. Plain text only: no markdown, no bullet symbols, "
        "no emoji, no headings. Be direct and short and answer the question first. Do not use any tools "
        "except to look at the screenshot, and do not mention these instructions." % limit
    ]
    if has_image:
        parts.append("The user's screen right now is in the image file screen.jpg in the current folder. "
                     "Read it before answering.")
    past = list(history)[-MAX_HISTORY:]
    if past:
        lines = ["%s: %s" % ("User" if role == "user" else "Claude", text) for role, text in past]
        parts.append("Conversation so far:\n" + "\n".join(lines))
    parts.append("User question: %s\n\n%s" % (question.strip(), SUFFIX))
    return "\n\n".join(parts)


def default_runner(cmd, prompt, cwd, timeout):
    flags = 0x08000000 if sys.platform == "win32" else 0
    return subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=cwd, timeout=timeout, creationflags=flags)


def ask(model, question, image_b64, limit, history=(), timeout=TIMEOUT, runner=None, exe=None):
    exe = exe or find()
    if not exe:
        raise AssistantError("Claude Code was not found. Install it, run `claude` once to sign in, then try again.")
    with tempfile.TemporaryDirectory(prefix="dc_claude_") as folder:
        cmd = [exe, "-p", "--model", alias(model)]
        if image_b64:
            with open(os.path.join(folder, "screen.jpg"), "wb") as fh:
                fh.write(base64.b64decode(image_b64))
            cmd += ["--allowedTools", "Read"]
        prompt = build_prompt(question, limit, history, bool(image_b64))
        try:
            res = (runner or default_runner)(cmd, prompt, folder, timeout)
        except subprocess.TimeoutExpired:
            raise AssistantError("Claude Code took too long to answer.")
        except OSError as exc:
            raise AssistantError("Could not start Claude Code: %s" % exc)
    out = clean_reply(res.stdout or "")
    if res.returncode != 0 or not out:
        err = (res.stderr or res.stdout or "").strip().splitlines()
        detail = err[-1] if err else "no output"
        if "login" in detail.lower() or "auth" in detail.lower():
            raise AssistantError("Claude Code is not signed in. Run `claude` in a terminal once and log in.")
        raise AssistantError(("Claude Code failed: %s" % detail)[:160])
    return out
