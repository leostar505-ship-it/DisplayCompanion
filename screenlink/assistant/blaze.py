INSTANT = 100
MAX_LINES = 8

WEB_OPTIONAL = (
    "You can search the web, but only when the answer truly depends on current information you do not already "
    "know. For maths, game mechanics you know and general facts, answer straight away without searching."
)


def reasoning(lines):
    n = max(0, int(lines))
    if n == 0:
        return "Speed matters most. Reply with only the final answer: no working, no explanation."
    if n == 1:
        return ("Speed matters most. Answer immediately with no preamble, answer first, then at most one short line "
                "of working.")
    return ("Speed matters most. Answer immediately with no preamble, answer first, then at most %d short lines "
            "of working." % n)


def speed_label(value):
    return "Instant" if value >= INSTANT else "%d /s" % int(value)
