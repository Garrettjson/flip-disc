"""
Frame mapping functions - backward compatibility layer.

This module provides backward-compatible functions that delegate to the new
FrameMapper class. Gradually migrate callers to use FrameMapper directly.
"""

from __future__ import annotations

import logging
from typing import Dict
import numpy as np

from .config import DisplayConfig
from .frame_mapper import FrameMapper

logger = logging.getLogger(__name__)

# Global instance for backward compatibility
_frame_mapper = FrameMapper()


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
    return _frame_mapper.map_canvas_to_panels(
        canvas_bits, canvas_w, canvas_h, cfg.panels
    )


def create_test_pattern(config: DisplayConfig, pattern: str) -> bytes:
    """
    Create test pattern canvas data for the given display configuration.

    Args:
        config: DisplayConfig with canvas size
        pattern: Pattern type ("checkerboard", "border", "solid", "clear")

    Returns:
        bytes: Packed canvas bitmap ready for send_canvas_frame
    """
    return _frame_mapper.create_test_pattern(
        config.canvas_size.w, config.canvas_size.h, pattern
    )


# Deprecated functions - maintained for backward compatibility
def unpack_canvas_to_bool(
    canvas_bits: bytes, canvas_w: int, canvas_h: int
) -> np.ndarray:
    """Convert packed canvas bits to a boolean array of shape (H, W)."""
    return _frame_mapper._unpack_canvas_to_bool(canvas_bits, canvas_w, canvas_h)
