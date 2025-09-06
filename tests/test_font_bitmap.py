from pathlib import Path

import numpy as np

from media_pipeline.common.font import BitmapFont


def font_path() -> Path:
    # New location under assets/
    here = Path(__file__).resolve()
    return here.parents[1] / "assets" / "text" / "standard.bmp"


def test_bitmap_font_load_and_glyph_count():
    font = BitmapFont(font_path(), auto_trim=True)
    # Expect near-full ASCII printable set present
    assert font.glyph_count >= 90
    # Height should match configured glyph height
    row = font.render_text_row("A")
    assert row.shape[0] == font.letter_height


def test_space_width_and_letter_spacing():
    font = BitmapFont(font_path(), auto_trim=True)
    space = font.get(" ")
    # Default space width for 5px glyphs is max(1, 5//2) == 2
    assert 1 <= space.width <= 3

    a = font.get("A")
    w_space = space.width
    w_a = a.width

    row = font.render_text_row("A A", letter_spacing=1)
    # Width should be A + spacing + space + spacing + A
    expected = w_a + 1 + w_space + 1 + w_a
    assert row.shape[1] == expected


def test_trim_produces_variable_widths():
    font = BitmapFont(font_path(), auto_trim=True)
    narrow = font.get("I").width
    wide = font.get("M").width
    # Expect that a typically narrow glyph is not wider than a wide one
    assert 1 <= narrow <= wide <= font.letter_width
