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
