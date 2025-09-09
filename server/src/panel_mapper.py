from __future__ import annotations

import logging
from typing import Dict
import numpy as np

from .config import DisplayConfig

logger = logging.getLogger(__name__)

def update_panels(
    canvas_bits: bytes, canvas_w: int, canvas_h: int, cfg: DisplayConfig
) -> Dict[int, bytes]:
    """
    Map the full canvas bitfield to per-panel packed bitmaps.
    
    This function takes a full canvas bitmap and splits it into individual panel data
    based on the panel configuration, applying any necessary transformations.

    Args:
        canvas_bits: Packed 1-bit rows for the full canvas (MSB-first)
        canvas_w: Canvas width in pixels
        canvas_h: Canvas height in pixels
        cfg: Display topology and panel orientations

    Returns:
        Dict keyed by panel address with packed row-major bytes for each panel,
        padded to a whole number of bytes per row.
    """
    # Validate canvas dimensions
    if canvas_w != cfg.canvas_size.w or canvas_h != cfg.canvas_size.h:
        raise ValueError(f"Canvas dimensions {canvas_w}x{canvas_h} don't match config {cfg.canvas_size.w}x{cfg.canvas_size.h}")
    
    # Unpack canvas bits -> boolean array [H, W]
    stride = (canvas_w + 7) // 8
    expected_bytes = canvas_h * stride
    
    if len(canvas_bits) != expected_bytes:
        raise ValueError(f"Canvas bits length {len(canvas_bits)} doesn't match expected {expected_bytes}")
    
    canvas = np.unpackbits(
        np.frombuffer(canvas_bits, dtype=np.uint8).reshape((canvas_h, stride)),
        axis=1,
        bitorder="big",
    )[:, :canvas_w].astype(bool)

    logger.debug(f"Unpacked canvas: {canvas.shape}, {np.sum(canvas)} pixels on")

    out: Dict[int, bytes] = {}
    
    for panel in cfg.enabled_panels:
        try:
            # Extract panel region from canvas
            x0, y0 = panel.origin.x, panel.origin.y
            w, h = panel.size.w, panel.size.h
            
            # Check bounds
            if x0 + w > canvas_w or y0 + h > canvas_h:
                logger.warning(f"Panel {panel.id} extends beyond canvas bounds, skipping")
                continue
            
            # Extract panel data
            sub = canvas[y0 : y0 + h, x0 : x0 + w]
            
            # Apply orientation transformation
            orientation = (panel.orientation or "normal").lower()
            sub = _apply_orientation(sub, orientation)
            
            # Pad width to multiple of 8 columns, then pack MSB-first per row
            actual_w = sub.shape[1]  # Width after orientation transforms
            pad_cols = (-actual_w) % 8
            
            if pad_cols > 0:
                sub_pad = np.pad(sub, ((0, 0), (0, pad_cols)), mode="constant", constant_values=False)
            else:
                sub_pad = sub
            
            # Pack into bytes
            packed_data = np.packbits(sub_pad, axis=1, bitorder="big").tobytes()
            out[panel.address] = packed_data
            
            pixels_on = np.sum(sub)
            total_pixels = sub.size
            logger.debug(f"Panel '{panel.id}' (addr {panel.address}): {pixels_on}/{total_pixels} pixels on, {len(packed_data)} bytes")
            
        except Exception as e:
            logger.error(f"Failed to process panel '{panel.id}': {e}")
            continue
    
    logger.info(f"Generated frame data for {len(out)} panels")
    return out


def _apply_orientation(sub: np.ndarray, orientation: str) -> np.ndarray:
    """
    Apply orientation transformation to panel data.
    
    Args:
        sub: Boolean array of panel pixel data
        orientation: Orientation string ("normal", "rot90", "rot180", "rot270", "fliph", "flipv")
        
    Returns:
        Transformed array
    """
    if orientation == "rot90":
        return np.rot90(sub, k=3)  # k=3 for clockwise 90°
    elif orientation == "rot180":
        return np.rot90(sub, k=2)
    elif orientation == "rot270":
        return np.rot90(sub, k=1)  # k=1 for clockwise 270° (counter-clockwise 90°)
    elif orientation == "fliph":
        return np.fliplr(sub)
    elif orientation == "flipv":
        return np.flipud(sub)
    elif orientation == "normal":
        return sub
    else:
        logger.warning(f"Unknown orientation '{orientation}', using normal")
        return sub


def to_column_bytes(packed: bytes, w: int, h: int) -> bytes:
    """
    Fold packed rows into per-column bytes for a w×h panel (MSB is top).

    This produces one byte per column, useful for hardware protocols that
    shift a column at a time.
    
    Args:
        packed: Packed row-major bytes from update_panels()
        w: Panel width in pixels
        h: Panel height in pixels
        
    Returns:
        Column-major packed bytes (one byte per column)
    """
    # Unpack panel-local packed rows to [H, W] then fold each column into a byte (top bit first)
    stride = (w + 7) // 8
    expected_bytes = h * stride
    
    if len(packed) != expected_bytes:
        raise ValueError(f"Packed data length {len(packed)} doesn't match expected {expected_bytes}")
    
    bits = np.unpackbits(
        np.frombuffer(packed, dtype=np.uint8).reshape((h, stride)),
        axis=1,
        bitorder="big",
    )[:, :w].astype(np.uint8)
    
    # Create bit weights (MSB first: 2^(h-1), 2^(h-2), ..., 2^1, 2^0)
    weights = 1 << np.arange(h - 1, -1, -1, dtype=np.uint16)
    
    # Compute column values (transpose to get columns, then dot product with weights)
    vals = bits.T.dot(weights).clip(0, 255).astype(np.uint8)
    
    return vals.tobytes()


def create_test_pattern(cfg: DisplayConfig, pattern: str = "checkerboard") -> bytes:
    """
    Create a test pattern for the entire canvas.
    
    Args:
        cfg: Display configuration
        pattern: Pattern type ("checkerboard", "border", "gradient", "solid")
        
    Returns:
        Packed canvas bitmap bytes
    """
    w, h = cfg.canvas_size.w, cfg.canvas_size.h
    canvas = np.zeros((h, w), dtype=bool)
    
    if pattern == "checkerboard":
        # Create checkerboard pattern
        for y in range(h):
            for x in range(w):
                canvas[y, x] = (x + y) % 2 == 0
    
    elif pattern == "border":
        # Create border pattern
        canvas[0, :] = True  # top
        canvas[-1, :] = True  # bottom
        canvas[:, 0] = True  # left
        canvas[:, -1] = True  # right
    
    elif pattern == "gradient":
        # Create horizontal gradient
        for x in range(w):
            if x % 4 < 2:  # Every other pair of columns
                canvas[:, x] = True
    
    elif pattern == "solid":
        # Solid fill
        canvas.fill(True)
    
    else:
        logger.warning(f"Unknown pattern '{pattern}', using checkerboard")
        return create_test_pattern(cfg, "checkerboard")
    
    # Pack into bytes
    stride = (w + 7) // 8
    padded_canvas = np.zeros((h, stride * 8), dtype=bool)
    padded_canvas[:, :w] = canvas
    
    packed = np.packbits(padded_canvas, axis=1, bitorder="big")
    return packed.tobytes()


def unpack_canvas_from_bytes(canvas_bits: bytes, canvas_w: int, canvas_h: int) -> np.ndarray:
    """
    Unpack canvas bytes back into a boolean array for debugging/visualization.
    
    Args:
        canvas_bits: Packed canvas bitmap bytes
        canvas_w: Canvas width in pixels
        canvas_h: Canvas height in pixels
        
    Returns:
        Boolean array of shape (canvas_h, canvas_w)
    """
    stride = (canvas_w + 7) // 8
    expected_bytes = canvas_h * stride
    
    if len(canvas_bits) != expected_bytes:
        raise ValueError(f"Canvas bits length {len(canvas_bits)} doesn't match expected {expected_bytes}")
    
    canvas = np.unpackbits(
        np.frombuffer(canvas_bits, dtype=np.uint8).reshape((canvas_h, stride)),
        axis=1,
        bitorder="big",
    )[:, :canvas_w].astype(bool)
    
    return canvas