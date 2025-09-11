from __future__ import annotations

import logging
from typing import Dict
import numpy as np

from .config import DisplayConfig, PanelConfig
from .validation import validate_canvas_data_size, validate_canvas_region_bounds

logger = logging.getLogger(__name__)


def update_panels(
    canvas_bits: bytes, canvas_w: int, canvas_h: int, cfg: DisplayConfig
) -> Dict[int, np.ndarray]:
    """
    Map the full canvas bitfield to per-panel boolean arrays.

    Input canvas is a row-major packed bitfield (8 pixels/byte, MSB first).

    Returns:
        Dict[int, np.ndarray]: mapping `panel.address -> numpy boolean array`
        ready for transmission by the serial writer.
    """
    canvas = unpack_canvas_to_bool(canvas_bits, canvas_w, canvas_h)

    out: Dict[int, np.ndarray] = {}
    for p in cfg.panels:
        sub = _slice_canvas_for_panel(canvas, p)
        oriented = _orient_panel_bitmap(sub, p)
        out[p.address] = oriented
    return out


def unpack_canvas_to_bool(
    canvas_bits: bytes, canvas_w: int, canvas_h: int
) -> np.ndarray:
    """
    Convert packed canvas bits to a boolean array of shape (H, W).
    """
    validate_canvas_data_size(len(canvas_bits), canvas_w, canvas_h)
    stride = (canvas_w + 7) // 8

    arr = np.frombuffer(canvas_bits, dtype=np.uint8).reshape((canvas_h, stride))
    bits = np.unpackbits(arr, axis=1, bitorder="big")[:, :canvas_w]
    return bits.astype(bool, copy=False)


def _slice_canvas_for_panel(canvas: np.ndarray, panel: PanelConfig) -> np.ndarray:
    x0, y0 = panel.origin.x, panel.origin.y
    w, h = panel.size.w, panel.size.h

    # Bounds check with helpful error message
    H, W = canvas.shape
    validate_canvas_region_bounds(x0, y0, w, h, W, H, panel.id, panel.address)

    return canvas[y0 : y0 + h, x0 : x0 + w]


def _orient_panel_bitmap(sub: np.ndarray, panel: PanelConfig) -> np.ndarray:
    """
    Apply panel orientation to the sub-bitmap.

    Supported orientation strings: "normal", "rot180", "rot90", "rot270".
    (Aliases "cw"/"ccw" can be added here if your config uses them.)
    """
    o = (panel.orientation or "normal").lower()

    if o == "normal":
        return sub
    if o == "rot180":
        return np.flipud(np.fliplr(sub))
    if o in ("rot90", "cw", "rot90cw"):
        return np.rot90(sub, k=3)  # 90° clockwise
    if o in ("rot270", "ccw", "rot90ccw"):
        return np.rot90(sub, k=1)  # 90° counter-clockwise

    raise ValueError(
        f"Unsupported orientation '{panel.orientation}' for panel '{panel.id}'"
    )


def create_test_pattern(config, pattern: str) -> bytes:
    """
    Create test pattern canvas data for the given display configuration.
    
    Args:
        config: DisplayConfig with canvas size
        pattern: Pattern type ("checkerboard", "border", "solid", "clear")
        
    Returns:
        bytes: Packed canvas bitmap ready for send_canvas_frame
    """
    w, h = config.canvas_size.w, config.canvas_size.h
    canvas = np.zeros((h, w), dtype=bool)
    
    if pattern == "checkerboard":
        for y in range(h):
            for x in range(w):
                canvas[y, x] = (x + y) % 2 == 0
    elif pattern == "border":
        canvas[0, :] = True  # Top border
        canvas[-1, :] = True  # Bottom border
        canvas[:, 0] = True  # Left border
        canvas[:, -1] = True  # Right border
    elif pattern == "solid":
        canvas[:, :] = True
    elif pattern == "clear":
        canvas[:, :] = False
    else:
        raise ValueError(f"Unknown test pattern: {pattern}")
    
    # Pack canvas to bytes (this is an input to send_canvas_frame)
    return np.packbits(canvas, axis=1, bitorder="big").tobytes()
