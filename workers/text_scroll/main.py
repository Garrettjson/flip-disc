from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

import numpy as np

from workers.common.base import WorkerBase, DisplayInfo, Frame2D
from workers.common.font import BitmapFont, repo_root_from


WORKER_ID = "text-scroll"


@dataclass
class ScrollConfig:
    text: str = "HELLO FLIP-DISC"
    pps: float = 10.0  # pixels per second
    letter_spacing: int = 1


def load_font() -> BitmapFont:
    root = repo_root_from(Path(__file__))
    bmp = root / "src" / "assets" / "text" / "standard.bmp"
    return BitmapFont(
        bmp,
        ascii_start=32,
        letters=95,
        padding=1,
        margin=1,
        letter_width=5,
        letter_height=7,
        # The provided sprite sheet has light (white) foreground on dark background.
        # We want foreground=1 (black pixels on the viewer), so set foreground_is_dark=False.
        foreground_is_dark=False,
    )


def build_strip(font: BitmapFont, cfg: ScrollConfig, height: int) -> np.ndarray:
    row = font.render_text_row(cfg.text, letter_spacing=cfg.letter_spacing)
    strip = np.zeros((height, row.shape[1]), dtype=np.uint8)
    top = max(0, (height - font.letter_height) // 2)
    strip[top : top + font.letter_height, : row.shape[1]] = row
    return strip


def _cfg_from_dict(d: dict) -> ScrollConfig:
    try:
        text = str(d.get("text", "") or "").strip()
        pps = float(d.get("pps", 0) or 0)
        letter_spacing = int(d.get("letter_spacing", 1) or 1)
    except Exception:
        return ScrollConfig()
    return ScrollConfig(
        text=text if text else ScrollConfig.text,
        pps=pps if pps > 0 else ScrollConfig.pps,
        letter_spacing=max(0, letter_spacing),
    )


class TextScroll(WorkerBase):
    """Horizontal text scroller using a bitmap font.

    Polls its configuration from the orchestrator (text, pixels-per-second,
    letter spacing) and rebuilds the source strip when settings change.
    The strip is looped with a blank gap equal to the canvas width and
    a window is composed into the output frame each tick.
    """

    def __init__(self) -> None:
        super().__init__(
            WORKER_ID,
            size_policy="strict",
            preview_scale=20,
            preview_title="Text Scroll Preview",
        )
        self.font = load_font()
        self.strip: np.ndarray | None = None
        self.last_cfg: ScrollConfig | None = None
        self.last_height: int | None = None
        self.start_t: float | None = None

    def _ensure_strip(
        self, display: DisplayInfo, cfg: ScrollConfig, now: float
    ) -> None:
        """Rebuild the rendered text strip if inputs changed.

        Args:
        - display: DisplayInfo (height may affect vertical centering)
        - cfg: Parsed ScrollConfig
        - now: Current timestamp for reset logic
        """
        need_new = (
            self.strip is None
            or self.last_cfg is None
            or self.last_height != display.height
            or cfg.text != self.last_cfg.text
            or cfg.letter_spacing != self.last_cfg.letter_spacing
        )
        if need_new:
            self.strip = build_strip(self.font, cfg, display.height)
            self.last_cfg = cfg
            self.last_height = display.height
            self.start_t = now

    def render(self, t: float, display: DisplayInfo, cfg: dict) -> Frame2D:
        """Render a frame for time t.

        Args:
        - t: seconds since worker start
        - display: DisplayInfo (width/height)
        - cfg: raw config dict fetched from orchestrator
        """
        cfg = _cfg_from_dict(cfg)
        now = t if self.start_t is None else (self.start_t + t)
        self._ensure_strip(display, cfg, now)
        assert self.strip is not None

        w, h = display.width, display.height
        gap_w = w  # gap columns of empty space between repeats
        tiled_w = int(self.strip.shape[1]) + gap_w
        pps = max(0.0, cfg.pps)
        offset = int((t) * pps) % max(1, tiled_w)

        frame = np.zeros((h, w), dtype=np.uint8)
        for x in range(w):
            src_x = (offset + x) % tiled_w
            if src_x < self.strip.shape[1]:
                frame[:, x] = self.strip[:, src_x]
            else:
                # gap
                pass

        # Return a concrete, typed frame container
        return Frame2D.from_rows(frame.tolist())


def main() -> None:
    TextScroll().run()


if __name__ == "__main__":
    main()
