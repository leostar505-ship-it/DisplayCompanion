import json
import re
import urllib.error
import urllib.request

from . import blaze

URL = "https://api.anthropic.com/v1/messages"
VERSION = "2023-06-01"
SUFFIX = "Sent via Display Companion"
MAX_HISTORY = 6


class AssistantError(Exception):
    pass


def system_prompt(limit, has_image=True, allow_screen=False, fast=False, lines=1):
    text = (
        "You are Claude, answering through Display Companion, a tiny %d character text screen on the user's desk. "
        "Your whole reply must be at most %d characters. Use plain text only: no markdown, no bullet symbols, "
        "no emoji, no headings. Be direct and short, and answer the question first. If a screenshot is attached, "
        "it shows the user's screen right now." % (limit, limit)
    )
    if not has_image and allow_screen:
        text += (" No screenshot is attached. If you cannot answer without seeing the user's screen, reply with exactly "
                 "NEED_SCREEN and nothing else. Otherwise just answer.")
    elif not has_image:
        text += " Screenshot mode is off: no screenshot is attached, so ignore any photos or images and do not try to look at the screen."
    if fast:
        text += " " + blaze.reasoning(lines)
    return text


def user_text(question):
    return "%s\n\n%s" % (question.strip(), SUFFIX)


def build_body(model, question, image_b64, limit, history, allow_screen=False, fast=False, lines=1):
    content = []
    if image_b64:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}})
    content.append({"type": "text", "text": user_text(question)})
    messages = [{"role": r, "content": t} for r, t in list(history)[-MAX_HISTORY:]]
    messages.append({"role": "user", "content": content})
    return {
        "model": model,
        "max_tokens": max(96, min(1024, int(limit * 0.6))),
        "system": system_prompt(limit, bool(image_b64), allow_screen, fast, lines),
        "messages": messages,
    }


def clean_reply(text):
    text = re.sub(r"```[a-zA-Z0-9]*", "", text)
    text = text.replace("`", "")
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=re.S)
    text = re.sub(r"(?<!\w)\*(\S.*?)\*(?!\w)", r"\1", text, flags=re.S)
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.M)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def fit_chars(text, limit):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:-") + "..."


def error_message(code, body):
    detail = ""
    try:
        detail = json.loads(body).get("error", {}).get("message", "")
    except (ValueError, AttributeError):
        pass
    if code == 401:
        return "The API key was rejected. Check it in the Claude tab."
    if code == 429:
        return "Rate limited. Wait a moment and try again."
    if code in (500, 502, 503, 529):
        return "Claude is busy right now. Try again."
    return ("API error %d: %s" % (code, detail)).strip().rstrip(":")[:160]


def ask(key, model, question, image_b64, limit, history=(), timeout=60, opener=None, allow_screen=False, fast=False, lines=1):
    if not key:
        raise AssistantError("No API key yet. Paste one in the Claude tab.")
    body = json.dumps(build_body(model, question, image_b64, limit, history, allow_screen, fast, lines)).encode("utf-8")
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "content-type": "application/json",
        "x-api-key": key,
        "anthropic-version": VERSION,
    })
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", "replace")
        except Exception:
            raw = ""
        raise AssistantError(error_message(exc.code, raw))
    except (urllib.error.URLError, OSError) as exc:
        raise AssistantError("Could not reach Claude: %s" % getattr(exc, "reason", exc))
    except ValueError:
        raise AssistantError("Claude sent something unreadable.")
    parts = [b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text"]
    text = clean_reply("".join(parts))
    if not text:
        raise AssistantError("Claude sent an empty reply.")
    return text


HAIKU = "claude-haiku-5-5"


def classify(key, question, timeout=30, opener=None):
    from .smartshot import CLASSIFY_PROMPT, parse_verdict
    body = json.dumps({
        "model": HAIKU,
        "max_tokens": 5,
        "messages": [{"role": "user", "content": CLASSIFY_PROMPT % question.strip()}],
    }).encode("utf-8")
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "content-type": "application/json",
        "x-api-key": key,
        "anthropic-version": VERSION,
    })
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        raise AssistantError("Could not reach Claude: classifier")
    parts = [b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text"]
    return parse_verdict("".join(parts))
