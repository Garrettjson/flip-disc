"""Panel mapping utilities: split full-frame bits into per-panel bit arrays.

Assumptions:
- Simple grid of identical panels laid out in row-major order, no rotation.
- Canvas frame is a boolean numpy array of shape (height, width).
"""

import numpy as np

from flipdisc.config import DisplayConfig
from flipdisc.core.exceptions import FrameError


def split_canvas_bits_to_panels(
    canvas_bits: np.ndarray, cfg: DisplayConfig
) -> list[np.ndarray]:
    """
    Split a canvas boolean image into per-panel boolean images.

    Returns row-major list of arrays with shape (panel_h, panel_w).
    """
    expected_shape = (cfg.height, cfg.width)
    if canvas_bits.shape != expected_shape:
        raise FrameError(
            f"Canvas shape mismatch: expected {expected_shape}, got {canvas_bits.shape}"
        )

    panels: list[np.ndarray] = []
    for pr in range(cfg.rows):
        y0 = pr * cfg.panel_h
        y1 = y0 + cfg.panel_h
        for pc in range(cfg.columns):
            x0 = pc * cfg.panel_w
            x1 = x0 + cfg.panel_w
            panels.append(canvas_bits[y0:y1, x0:x1])
    return panels
