import numpy as np

from screenlink import fonts
from screenlink.protocol import HEIGHT, WIDTH


def test_long_text_wraps_inside_the_screen():
    font = fonts.load_font(None, 18)
    img = fonts.render_block("word " * 40, font, "#ffffff", "#000000", align="left", valign="top")
    arr = np.asarray(img)
    assert arr[:, WIDTH - 1].sum() == 0
    assert arr[:, :3].sum() > 0 or arr[:, 3:10].sum() > 0


def test_layout_counts_lines_and_rows():
    font = fonts.load_font(None, 18)
    lines, rows = fonts.layout("hi", font)
    assert lines == ["hi"]
    assert rows >= 3


def test_fitting_prefix_cuts_overflow():
    font = fonts.load_font(None, 18)
    text = "lorem ipsum dolor sit amet " * 20
    keep = fonts.fitting_prefix(text, font)
    lines, rows = fonts.layout(text[:keep], font)
    assert 0 < keep < len(text)
    assert len(lines) <= rows
    more, _ = fonts.layout(text[:keep + 1], font)
    assert len(more) > rows


def test_auto_fit_picks_size_that_fits():
    size = fonts.fit_size("hello there my friend how are you today", None)
    font = fonts.load_font(None, size)
    lines, rows = fonts.layout("hello there my friend how are you today", font, 2)
    assert len(lines) <= rows
