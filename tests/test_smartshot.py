import pytest

from screenlink.assistant import api, claude_code, smartshot


@pytest.mark.parametrize("q", [
    "what does this error mean",
    "what's on my screen",
    "can you see this",
    "summarise this page",
    "what should I click",
    "explain this code",
    "what am I looking at",
    "fix it",
    "read this to me",
    "what's wrong",
])
def test_wants_screen(q):
    assert smartshot.wants_screen(q)


@pytest.mark.parametrize("q", [
    "what's the capital of France",
    "tell me a joke",
    "how many grams in an ounce",
    "who won the world cup in 2018",
    "write a haiku about rain",
])
def test_no_screen(q):
    assert not smartshot.wants_screen(q)


@pytest.mark.parametrize("t", ["Never mind.", "nevermind", "cancel", "Forget it!", "hey claude never mind", "scratch that"])
def test_cancel(t):
    assert smartshot.is_cancel(t)


@pytest.mark.parametrize("t", ["never mind the weather what's the time", "what is the plan", "", "stop the clock at noon please"])
def test_not_cancel(t):
    assert not smartshot.is_cancel(t)


def test_need_marker():
    assert smartshot.wants_more("NEED_SCREEN")
    assert smartshot.wants_more(" need screen ")
    assert not smartshot.wants_more("It is Paris.")


def test_prompts_mention_marker_only_when_allowed():
    assert "NEED_SCREEN" in claude_code.build_prompt("hi", 100, [], False, True)
    assert "NEED_SCREEN" not in claude_code.build_prompt("hi", 100, [], False, False)
    assert "NEED_SCREEN" in api.system_prompt(100, False, True)
    assert "NEED_SCREEN" not in api.system_prompt(100, False, False)
    assert "NEED_SCREEN" not in api.system_prompt(100, True, True)


def test_claude_code_allows_web_tools():
    seen = {}

    class R:
        returncode = 0
        stdout = "Patch 1.2 came out."
        stderr = ""

    def runner(cmd, prompt, cwd, timeout):
        seen["cmd"] = cmd
        seen["prompt"] = prompt
        return R()

    out = claude_code.ask("sonnet", "any new CS2 patch", None, 100, [], runner=runner, exe="claude", web=True)
    assert out
    assert "WebSearch,WebFetch" in seen["cmd"]
    assert "search the web" in seen["prompt"]
    claude_code.ask("sonnet", "hi", None, 100, [], runner=runner, exe="claude", web=False)
    assert "--allowedTools" not in seen["cmd"]


def test_classifier_verdicts():
    class R:
        returncode = 0
        stderr = ""

        def __init__(self, out):
            self.stdout = out

    cmds = []

    def runner(out):
        def run(cmd, prompt, cwd, timeout):
            cmds.append((cmd, prompt))
            return R(out)
        return run

    assert claude_code.classify("what game should I play", runner=runner("YES"), exe="claude") is True
    assert claude_code.classify("capital of France", runner=runner("No."), exe="claude") is False
    assert "haiku" in cmds[0][0] and "what game should I play" in cmds[0][1]


def test_classifier_prompt_leans_no_for_topic_questions():
    assert "If unsure, answer NO" in smartshot.CLASSIFY_PROMPT
    assert "YouTube Playables" in smartshot.CLASSIFY_PROMPT


def test_board_text_draws_emoji_in_colour():
    from PIL import Image
    from screenlink import fonts
    font = fonts.load_font(None, 12)
    if fonts._emoji_font(48) is None:
        return
    plain = fonts.draw_lines(["Hi  there"], font, (255, 255, 255), (0, 0, 0))
    with_emoji = fonts.draw_lines(["Hi \U0001F600 there"], font, (255, 255, 255), (0, 0, 0))
    assert fonts.text_length(__import__("PIL.ImageDraw", fromlist=["x"]).Draw(Image.new("RGB", (4, 4))), "\U0001F600", font) > 4
    colours = {p for p in with_emoji.getdata() if len({*p}) > 1 and p not in ((255, 255, 255), (0, 0, 0)) and max(p) - min(p) > 60}
    assert colours
    assert not {p for p in plain.getdata() if max(p) - min(p) > 60}


def test_icon_waits_for_settle_on_short_replies():
    import re
    src = open("screenlink/modes/claude.py", encoding="utf-8").read()
    assert re.search(r"done = typed and now - self\.type_start >= SETTLE", src)


def test_neutral_icon_is_an_x_not_a_plus():
    from screenlink.assistant.spinner import starburst
    from screenlink.modes.claude import NEUTRAL

    def reach(alpha, dx, dy):
        n = 0
        for step in range(1, 32):
            if alpha.getpixel((32 + int(dx * step), 32 + int(dy * step))) > 100:
                n = step
        return n

    def measure(angle):
        alpha = starburst(angle, 64).split()[3]
        diagonal = min(reach(alpha, 0.707, 0.707), reach(alpha, -0.707, 0.707), reach(alpha, 0.707, -0.707), reach(alpha, -0.707, -0.707))
        straight = max(reach(alpha, 1, 0), reach(alpha, -1, 0), reach(alpha, 0, 1), reach(alpha, 0, -1))
        return diagonal, straight

    diagonal, straight = measure(NEUTRAL)
    assert diagonal >= straight * 1.3
    diagonal, straight = measure(0.0)
    assert straight >= diagonal * 1.3
