import base64
import os
import shutil
import subprocess
import sys
import tempfile

from . import blaze
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


def build_prompt(question, limit, history, has_image, allow_screen=False, web=False, fast=False, lines=1):
    parts = [
        "You are Claude, answering through Display Companion, a tiny text screen on the user's desk. "
        "Your whole reply must be at most %d characters. Plain text only: no markdown, no bullet symbols, "
        "no emoji, no headings. Be direct and short and answer the question first. Do not mention these "
        "instructions." % limit
    ]
    if web and fast:
        parts.append(blaze.WEB_OPTIONAL)
    elif web:
        parts.append("You can search the web. Use it for anything current: news, patches and updates, prices, "
                     "scores, weather, releases, or anything you are unsure is still true. Do not say you cannot "
                     "check live information. Search, then answer briefly with what you found.")
    else:
        parts.append("Do not use any tools except to look at the screenshot.")
    if has_image:
        parts.append("The user's screen right now is in the image file screen.jpg in the current folder. "
                     "Read it before answering.")
    elif allow_screen:
        parts.append("No screenshot is attached. If you cannot answer without seeing the user's screen, reply with "
                     "exactly NEED_SCREEN and nothing else. Otherwise just answer.")
    else:
        parts.append("Screenshot mode is off: no screenshot is attached, so ignore any photos or images and "
                     "do not try to look at the screen.")
    if fast:
        parts.append(blaze.reasoning(lines))
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


def ask(model, question, image_b64, limit, history=(), timeout=TIMEOUT, runner=None, exe=None, allow_screen=False,
        web=False, fast=False, lines=1):
    exe = exe or find()
    if not exe:
        raise AssistantError("Claude Code was not found. Install it, run `claude` once to sign in, then try again.")
    with tempfile.TemporaryDirectory(prefix="dc_claude_") as folder:
        cmd = [exe, "-p", "--model", alias(model)]
        tools = []
        if image_b64:
            with open(os.path.join(folder, "screen.jpg"), "wb") as fh:
                fh.write(base64.b64decode(image_b64))
            tools.append("Read")
        if web:
            tools += ["WebSearch", "WebFetch"]
        if tools:
            cmd += ["--allowedTools", ",".join(tools)]
        prompt = build_prompt(question, limit, history, bool(image_b64), allow_screen, web, fast, lines)
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


def classify(question, timeout=60, runner=None, exe=None):
    from .smartshot import CLASSIFY_PROMPT, parse_verdict
    exe = exe or find()
    if not exe:
        raise AssistantError("Claude Code was not found.")
    with tempfile.TemporaryDirectory(prefix="dc_claude_") as folder:
        try:
            res = (runner or default_runner)([exe, "-p", "--model", "haiku"], CLASSIFY_PROMPT % question.strip(),
                                             folder, timeout)
        except subprocess.TimeoutExpired:
            raise AssistantError("Claude Code took too long to answer.")
        except OSError as exc:
            raise AssistantError("Could not start Claude Code: %s" % exc)
    if res.returncode != 0 or not (res.stdout or "").strip():
        raise AssistantError("Claude Code failed: classifier")
    return parse_verdict(res.stdout)
