"""Tests for bitmap font loading and text rendering."""

import numpy as np
import pytest

from flipdisc.fonts.loader import BitmapFont, load_font


def test_glyph_loading():
    font = BitmapFont()
    # ASCII 32-126 = 95 printable characters
    assert len(font._glyphs) == 95
    for char, glyph in font._glyphs.items():
        assert glyph.shape == (7, 5), f"Glyph '{char}' has wrong shape: {glyph.shape}"
        assert glyph.dtype == np.float32


def test_get_glyph_fallback():
    font = BitmapFont()
    # Unknown character should return space glyph
    space = font.get_glyph(" ")
    unknown = font.get_glyph("\x80")
    np.testing.assert_array_equal(unknown, space)


def test_render_line_dimensions():
    font = BitmapFont()
    result = font.render_line("AB", spacing=1)
    # 2 chars * 5px wide + 1px spacing = 11px
    assert result.shape == (7, 11)
    assert result.dtype == np.float32


def test_render_line_single_char():
    font = BitmapFont()
    result = font.render_line("A", spacing=1)
    assert result.shape == (7, 5)


def test_render_line_empty():
    font = BitmapFont()
    result = font.render_line("")
    assert result.shape == (7, 0)


def test_render_wrapped_basic():
    font = BitmapFont()
    # "HI" is 11px wide (5+1+5), fits in 28px
    result = font.render_wrapped("HI", max_width=28)
    assert result.shape[1] == 28
    assert result.shape[0] == 7  # single line


def test_render_wrapped_multiline():
    font = BitmapFont()
    # Each char is 5px + 1px spacing. "HELLO WORLD" should wrap
    # "HELLO" = 5*5 + 4*1 = 29px, wider than 28
    # "HI AB" = "HI" fits (11px), "AB" fits (11px) -> 2 lines
    result = font.render_wrapped("HI AB", max_width=15)
    assert result.shape[1] == 15
    # "HI" (11px) fits, "AB" (11px) fits -> 2 lines: 7 + 1 + 7 = 15
    assert result.shape[0] == 15


def test_render_wrapped_respects_max_width():
    font = BitmapFont()
    result = font.render_wrapped("ABCDEF GHIJKL", max_width=28)
    assert result.shape[1] == 28
    # No column should exceed max_width
    assert result.shape[1] <= 28


def test_hyphenation_long_word():
    font = BitmapFont()
    # A word that's too wide for max_width should be hyphenated
    result = font.render_wrapped("ABCDEFGHIJKLMNOP", max_width=28)
    assert result.shape[1] == 28
    # Should produce multiple lines
    assert result.shape[0] > 7


def test_render_line_spacing_zero():
    font = BitmapFont()
    result = font.render_line("AB", spacing=0)
    assert result.shape == (7, 10)  # 2 * 5px, no spacing


# --- load_font ---


def test_load_font_standard():
    font = load_font("standard")
    assert font.letter_width == 5
    assert font.letter_height == 7
    assert len(font._glyphs) == 95


def test_load_font_compact():
    font = load_font("compact")
    assert font.letter_width == 3
    assert font.letter_height == 5
    assert font.get_glyph("A").shape == (5, 3)
    assert font.get_glyph(" ").sum() == 0  # space is a blank glyph


def test_compact_glyph_y():
    """'y' pixel pattern: top merge, then descender curving left."""
    font = load_font("compact")
    glyph = (font.get_glyph("y") > 0.5).astype(int).tolist()
    expected = [
        [0, 0, 0],
        [1, 0, 1],
        [1, 1, 1],
        [0, 0, 1],
        [1, 1, 0],
    ]
    assert glyph == expected, f"Unexpected 'y' shape:\n{glyph}"


def test_load_font_unknown_raises():
    with pytest.raises(KeyError, match="unknown"):
        load_font("unknown")
