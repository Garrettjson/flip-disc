"""
Pure Frame Mapping Logic

This module contains the FrameMapper class, which handles all pure frame mapping
operations without any I/O dependencies. It converts canvas bitmaps to per-panel
arrays and handles test pattern generation.

Pure class with no side effects - easily testable and reusable.
"""

from __future__ import annotations

from typing import Dict, TYPE_CHECKING
import numpy as np

from .validation import validate_canvas_data_size, validate_canvas_region_bounds

if TYPE_CHECKING:
    from .config import PanelConfig


class FrameMapper:
    """
    Pure frame mapping operations for flip-disc displays.

    This class contains no I/O operations and no side effects - all methods are
    pure functions that take inputs and return outputs without modifying state.
    """

    def map_canvas_to_panels(
        self,
        canvas_bits: bytes,
        canvas_w: int,
        canvas_h: int,
        panels: list["PanelConfig"],
    ) -> Dict[int, np.ndarray]:
        """
        Map the full canvas bitfield to per-panel boolean arrays.

        Input canvas is a row-major packed bitfield (8 pixels/byte, MSB first).

        Args:
            canvas_bits: Packed bitmap for entire canvas
            canvas_w: Canvas width in pixels
            canvas_h: Canvas height in pixels
            panels: List of panel configurations

        Returns:
            Dict[int, np.ndarray]: mapping `panel.address -> numpy boolean array`
            ready for transmission by the serial writer.
        """
        canvas = self._unpack_canvas_to_bool(canvas_bits, canvas_w, canvas_h)

        panel_arrays: Dict[int, np.ndarray] = {}
        for panel in panels:
            sub = self._slice_canvas_for_panel(canvas, panel)
            oriented = self._orient_panel_bitmap(sub, panel)
            panel_arrays[panel.address] = oriented

        return panel_arrays

    def create_test_pattern(self, canvas_w: int, canvas_h: int, pattern: str) -> bytes:
        """
        Create test pattern canvas data for the given canvas dimensions.

        Args:
            canvas_w: Canvas width in pixels
            canvas_h: Canvas height in pixels
            pattern: Pattern type ("checkerboard", "border", "solid", "clear")

        Returns:
            bytes: Packed canvas bitmap ready for map_canvas_to_panels

        Raises:
            ValueError: If pattern type is unknown
        """
        canvas = np.zeros((canvas_h, canvas_w), dtype=bool)

        if pattern == "checkerboard":
            for y in range(canvas_h):
                for x in range(canvas_w):
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

        # Pack canvas to bytes
        return np.packbits(canvas, axis=1, bitorder="big").tobytes()

    def _unpack_canvas_to_bool(
        self, canvas_bits: bytes, canvas_w: int, canvas_h: int
    ) -> np.ndarray:
        """
        Convert packed canvas bits to a boolean array of shape (H, W).

        Args:
            canvas_bits: Packed bitmap data
            canvas_w: Canvas width in pixels
            canvas_h: Canvas height in pixels

        Returns:
            np.ndarray: Boolean array of shape (canvas_h, canvas_w)

        Raises:
            ValidationError: If canvas data size doesn't match expected dimensions
        """
        validate_canvas_data_size(len(canvas_bits), canvas_w, canvas_h)
        stride = (canvas_w + 7) // 8

        arr = np.frombuffer(canvas_bits, dtype=np.uint8).reshape((canvas_h, stride))
        bits = np.unpackbits(arr, axis=1, bitorder="big")[:, :canvas_w]
        return bits.astype(bool, copy=False)

    def _slice_canvas_for_panel(
        self, canvas: np.ndarray, panel: "PanelConfig"
    ) -> np.ndarray:
        """
        Extract the canvas region corresponding to a panel.

        Args:
            canvas: Full canvas boolean array
            panel: Panel configuration

        Returns:
            np.ndarray: Canvas slice for the panel

        Raises:
            ValidationError: If panel region is out of canvas bounds
        """
        x0, y0 = panel.origin.x, panel.origin.y
        w, h = panel.size.w, panel.size.h

        # Bounds check with helpful error message
        canvas_h, canvas_w = canvas.shape
        validate_canvas_region_bounds(
            x0, y0, w, h, canvas_w, canvas_h, panel.id, panel.address
        )

        return canvas[y0 : y0 + h, x0 : x0 + w]

    def _orient_panel_bitmap(self, sub: np.ndarray, panel: "PanelConfig") -> np.ndarray:
        """
        Apply panel orientation to the sub-bitmap.

        Args:
            sub: Panel bitmap slice
            panel: Panel configuration with orientation

        Returns:
            np.ndarray: Oriented bitmap

        Raises:
            ValueError: If orientation is unsupported
        """
        orientation = (panel.orientation or "normal").lower()

        if orientation == "normal":
            return sub
        elif orientation == "rot180":
            return np.flipud(np.fliplr(sub))
        elif orientation in ("rot90", "cw", "rot90cw"):
            return np.rot90(sub, k=3)  # 90° clockwise
        elif orientation in ("rot270", "ccw", "rot90ccw"):
            return np.rot90(sub, k=1)  # 90° counter-clockwise
        else:
            raise ValueError(
                f"Unsupported orientation '{panel.orientation}' for panel '{panel.id}'"
            )
