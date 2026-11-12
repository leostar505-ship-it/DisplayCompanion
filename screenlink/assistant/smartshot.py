import re

NEED = "NEED_SCREEN"

NOUNS = (
    "error|errors|code|text|image|picture|photo|video|game|menu|button|message|email|file|website|site|app|program|"
    "document|chart|graph|table|problem|question|word|sentence|paragraph|page|tab|window|screen|popup|dialog|"
    "setting|settings|result|results|line|function|bug|warning|notification|list|form|link|post|comment|recipe|"
    "level|map|enemy|boss|puzzle|slide|spreadsheet|email|thread|chat|song|track|number|price"
)
PATTERNS = [
    r"\b(my|the|this|that|current)\s+(screen|monitor|display|desktop|window|tab)\b",
    r"\bscreenshot\b",
    r"\b(this|that|these|those)\s+(%s)\b" % NOUNS,
    r"\b(look|looking|looks|see|seeing|read|check|watch|watching)\s+(at\s+)?(this|that|it|my|the|here|what)\b",
    r"\bwhat('s| is| am i| are you)\s+(this|that|these|those|here|on|in front|looking|seeing)\b",
    r"\bwhat\s+does\s+(this|that|it)\s+(say|mean|do|show)\b",
    r"\b(explain|summari[sz]e|translate|describe|solve|fix|debug|answer|help me with|rewrite|proofread)\s+(this|that|these|those|it|what)\b",
    r"\bwhat('s| is)\s+wrong\b",
    r"\bwhat\s+should\s+i\s+(click|press|do|pick|choose|select|type)\b",
    r"\b(on|in)\s+(my|the)\s+(screen|monitor|display|page|tab|window|game|app)\b",
    r"\b(right now|currently open|open right now|i'?m (on|in|using|playing|watching|reading))\b",
    r"\b(above|below|over here|up there|down there)\b",
    r"\bcan you see\b|\bdo you see\b|\bwhat do you see\b",
]
COMPILED = [re.compile(p, re.I) for p in PATTERNS]

BLAZE_PATTERNS = [
    r"\bscreen\s?shots?\b",
    r"\b(my|the|this)\s+(screen|monitor|display)\b",
    r"\bon\s+(my\s+|the\s+)?screen\b",
    r"\b(look|looking)\s+at\s+(this|that|my|the)\b",
    r"\bcan you see\b|\bdo you see\b|\bwhat do you see\b",
    r"\bwhat('s| is)\s+(this|that)\b",
]
BLAZE_COMPILED = [re.compile(p, re.I) for p in BLAZE_PATTERNS]

CANCEL = (
    "never mind", "nevermind", "never mind that", "cancel", "cancel that", "forget it", "forget that",
    "scratch that", "ignore that", "stop", "abort", "no thanks", "nope", "oops", "my bad",
)


def wants_screen(question):
    text = " ".join(str(question).lower().split())
    return any(p.search(text) for p in COMPILED)


def blaze_wants_screen(question):
    text = " ".join(str(question).lower().split())
    return any(p.search(text) for p in BLAZE_COMPILED)


FILLERS = {
    "um", "uh", "uhh", "umm", "er", "erm", "hmm", "hm", "oh", "ah", "ok", "okay", "yeah", "yep", "so", "just",
    "actually", "wait", "sorry", "please", "no", "well",
}
LEADS = ("hey claude", "okay claude", "ok claude", "hi claude", "claude")
CANCEL_PHRASES = sorted({c for c in CANCEL if " " in c} | {"never mind", "forget it", "scratch that"}, key=len, reverse=True)
CANCEL_SINGLE = {"nevermind", "cancel", "stop", "abort", "nope", "oops"}


def _strip_fillers(words):
    out = list(words)
    while out and out[0] in FILLERS:
        out.pop(0)
    while out and out[-1] in FILLERS:
        out.pop()
    return out


def is_cancel(text):
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in str(text).lower())
    cleaned = " ".join(cleaned.split())
    if not cleaned or len(cleaned.split()) > 8:
        return False
    for lead in LEADS:
        if cleaned.startswith(lead + " ") or cleaned == lead:
            cleaned = cleaned[len(lead):].strip()
            break
    words = _strip_fillers(cleaned.split())
    if not words:
        return False
    phrase = " ".join(words)
    squashed = phrase.replace(" ", "")
    if phrase in CANCEL or squashed in {c.replace(" ", "") for c in CANCEL}:
        return True
    for c in CANCEL_PHRASES + ["nevermind"]:
        if phrase.endswith(" " + c):
            return True
    rest = phrase
    changed = True
    while rest and changed:
        changed = False
        for c in CANCEL_PHRASES + sorted(CANCEL_SINGLE):
            if rest == c or rest.startswith(c + " "):
                rest = rest[len(c):].strip()
                changed = True
                break
        rest = " ".join(_strip_fillers(rest.split()))
    return not rest


def wants_more(reply):
    return str(reply).strip().upper().replace(" ", "_").startswith(NEED)


CLASSIFY_PROMPT = (
    "You are a router. Decide whether the answer depends on what is currently on the user's computer screen. "
    "Answer YES only if the question points at something on their screen or in their current situation: it says "
    "this, that, here or it about something visible, asks what to click or do next in an app, asks you to read, "
    "describe, fix or check something they are looking at, or asks for a personal recommendation about what they "
    "should play, watch or do right now. Answer NO for questions about a topic, a fact, an opinion, a why or how "
    "explanation, maths, writing or chat, even if the question names a website, game or app (for example 'why is "
    "there so much AI slop on YouTube Playables' is NO). If unsure, answer NO. "
    "Reply with exactly one word: YES or NO.\n\nQuestion: %s"
)


def parse_verdict(text):
    return str(text).strip().upper().startswith("YES")
