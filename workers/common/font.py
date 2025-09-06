from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

import numpy as np
from PIL import Image, ImageFont, ImageDraw
import warnings


@dataclass
class Glyph:
    char: str
    bitmap: np.ndarray  # shape: (height, width), dtype=uint8 values {0,1}
    width: int
    height: int


class BitmapFont:
    """
    Lightweight bitmap font loader for the provided sprite sheet
    at `src/assets/text/standard.bmp`.

    The sheet is a grid of glyphs with a 1px padding border and 1px
    margin between glyphs. Default glyph size is 5x7, starting at
    ASCII 32 (space), for 95 printable characters.

    Uses Pillow to avoid adding OpenCV as a dependency.
    """

    def __init__(
        self,
        image_path: Path,
        *,
        ascii_start: int = 32,
        letters: int = 95,
        padding: int = 1,
        margin: int = 1,
        letter_width: int = 5,
        letter_height: int = 7,
        foreground_is_dark: bool = True,
        auto_trim: bool = True,
        space_width: int | None = None,
    ) -> None:
        self.ascii_start = ascii_start
        self.letters = letters
        self.padding = padding
        self.margin = margin
        self.letter_width = letter_width
        self.letter_height = letter_height

        img = Image.open(image_path).convert("L")
        arr = np.array(img, dtype=np.uint8)
        # Convert to binary: foreground (ink) vs background. The provided
        # bitmap has dark foreground on light background.
        if foreground_is_dark:
            bits = (arr < 128).astype(np.uint8)
        else:
            bits = (arr >= 128).astype(np.uint8)

        self._glyphs: Dict[str, Glyph] = {}

        h, w = bits.shape
        gw, gh = letter_width, letter_height
        i = 0

        # Basic sheet validation (non-fatal): check we have enough room for rows/cols
        if w < padding + gw or h < padding + gh:
            raise ValueError(
                f"bitmap too small: {w}x{h} for glyph {gw}x{gh} with padding {padding}"
            )
        # Use stepping that matches src/utils/text.py: start at `padding` and step
        # by `letter_size + padding + margin`.
        row_step = gh + padding + margin
        col_step = gw + padding + margin
        max_y = h - gh - padding
        max_x = w - gw - padding
        for y in range(padding, max(0, max_y) + 1, row_step):
            for x in range(padding, max(0, max_x) + 1, col_step):
                if i >= letters:
                    break
                ch = chr(ascii_start + i)
                crop = bits[y : y + gh, x : x + gw].astype(np.uint8)
                if auto_trim:
                    cols = crop.any(axis=0)
                    if cols.any():
                        left = int(np.argmax(cols))
                        right = int(len(cols) - 1 - np.argmax(cols[::-1]))
                        crop = crop[:, left : right + 1]
                width = int(crop.shape[1])
                if ch == " ":
                    # ensure visible spacing for space
                    sw = space_width if space_width is not None else max(1, gw // 2)
                    crop = np.zeros((gh, sw), dtype=np.uint8)
                    width = sw
                self._glyphs[ch] = Glyph(ch, crop, width, gh)
                i += 1
            if i >= letters:
                break

        # Ensure space exists even if not present
        if " " not in self._glyphs:
            sw = space_width if space_width is not None else max(1, gw // 2)
            self._glyphs[" "] = Glyph(" ", np.zeros((gh, sw), dtype=np.uint8), sw, gh)

        # Final validation: number of glyphs
        if len(self._glyphs) < min(letters, 95):
            warnings.warn(
                f"loaded only {len(self._glyphs)} glyphs (expected around {letters}); check sheet layout and params",
                RuntimeWarning,
            )

    def get(self, ch: str) -> Glyph:
        # Fallback to space for unknown glyphs
        return self._glyphs.get(
            ch, self._glyphs.get(" ", next(iter(self._glyphs.values())))
        )

    @property
    def glyph_count(self) -> int:
        return len(self._glyphs)

    def render_text_row(self, text: str, letter_spacing: int = 1) -> np.ndarray:
        """
        Render text into a single-row bitmap of height `letter_height` and
        width equal to sum of glyph widths plus spacing.
        Returns array of shape (letter_height, total_width) with 0/1 values.
        """
        if not text:
            return np.zeros((self.letter_height, 0), dtype=np.uint8)
        parts: list[np.ndarray] = []
        first = True
        for ch in text:
            g = self.get(ch)
            if not first:
                parts.append(
                    np.zeros(
                        (self.letter_height, max(0, int(letter_spacing))),
                        dtype=np.uint8,
                    )
                )
            parts.append(g.bitmap)
            first = False
        return (
            np.concatenate(parts, axis=1)
            if parts
            else np.zeros((self.letter_height, 0), dtype=np.uint8)
        )


def repo_root_from(file: Path) -> Path:
    # workers/common/font.py -> workers/common -> workers -> repo root
    return file.resolve().parents[2]


class TTFFont:
    """
    Optional TTF-based font renderer using Pillow. Not used by default.

    Renders ASCII 32..(32+letters-1) to binary bitmaps at a target pixel height.
    Each glyph is auto-trimmed horizontally to variable width.
    """

    def __init__(
        self,
        font_path: Path,
        *,
        pixel_height: int = 10,
        ascii_start: int = 32,
        letters: int = 95,
        threshold: int = 128,
        pad_x: int = 1,
        pad_y: int = 1,
        space_width: int | None = None,
    ) -> None:
        self.ascii_start = ascii_start
        self.letters = letters
        self.letter_height = pixel_height
        self._glyphs: Dict[str, Glyph] = {}

        font = ImageFont.truetype(str(font_path), size=pixel_height)

        for i in range(letters):
            ch = chr(ascii_start + i)
            # Render onto a generous canvas
            w = pixel_height * 3
            h = pixel_height + pad_y * 2
            img = Image.new("L", (w, h), 0)
            draw = ImageDraw.Draw(img)
            draw.text((pad_x, pad_y), ch, font=font, fill=255)
            arr = np.array(img, dtype=np.uint8)
            bits = (arr >= threshold).astype(np.uint8)
            # Trim horizontally to content; keep fixed height
            cols = bits.any(axis=0)
            if cols.any():
                left = int(np.argmax(cols))
                right = int(len(cols) - 1 - np.argmax(cols[::-1]))
                crop = bits[:, left : right + 1]
            else:
                crop = np.zeros((h, 1), dtype=np.uint8)
            # Normalize to target letter height by cropping/padding vertically around content
            if crop.shape[0] != self.letter_height:
                if crop.shape[0] > self.letter_height:
                    top = max(0, (crop.shape[0] - self.letter_height) // 2)
                    crop = crop[top : top + self.letter_height, :]
                else:
                    pad_top = (self.letter_height - crop.shape[0]) // 2
                    pad_bot = self.letter_height - crop.shape[0] - pad_top
                    crop = np.pad(crop, ((pad_top, pad_bot), (0, 0)), mode="constant")
            gw = crop.shape[1]
            if ch == " ":
                sw = (
                    space_width
                    if space_width is not None
                    else max(1, pixel_height // 3)
                )
                crop = np.zeros((self.letter_height, sw), dtype=np.uint8)
                gw = sw
            self._glyphs[ch] = Glyph(ch, crop, gw, self.letter_height)

    def get(self, ch: str) -> Glyph:
        return self._glyphs.get(
            ch, self._glyphs.get(" ", next(iter(self._glyphs.values())))
        )

    def render_text_row(self, text: str, letter_spacing: int = 1) -> np.ndarray:
        if not text:
            return np.zeros((self.letter_height, 0), dtype=np.uint8)
        parts: list[np.ndarray] = []
        first = True
        for ch in text:
            g = self.get(ch)
            if not first:
                parts.append(
                    np.zeros(
                        (self.letter_height, max(0, int(letter_spacing))),
                        dtype=np.uint8,
                    )
                )
            parts.append(g.bitmap)
            first = False
        return (
            np.concatenate(parts, axis=1)
            if parts
            else np.zeros((self.letter_height, 0), dtype=np.uint8)
        )
