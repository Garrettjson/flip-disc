"""Protocol encoder for Flipdots panels based on PROTOCOL.md.

Frame format (general): 0x80 <CMD> <ADDR> <DATA...> 0x8F

Flush: 0x80 0x82 0x8F

Data for panel frames: width bytes, one per column. Each byte packs 7 bits
for a 7-pixel-tall column: bit0=top pixel, bit6=bottom pixel, bit7 must be 0.
"""


import numpy as np


def _cmd_for_panel_width(panel_w: int, refresh: bool) -> int:
    """Return command byte for given panel width and refresh mode."""
    if panel_w == 28:
        return 0x83 if refresh else 0x84
    if panel_w == 14:
        return 0x92 if refresh else 0x93
    if panel_w == 7:
        # NO (buffered) not supported by 7x7 per spec; force refresh
        return 0x87
    raise ValueError(f"Unsupported panel width: {panel_w}")


def panel_bits_to_column_bytes(panel_bits: np.ndarray) -> bytes:
    """Pack panel boolean image (H=7) to column bytes (vectorized).

    - LSB=top pixel, bit7=0 per spec.
    - Returns W bytes; W in {7, 14, 28}.
    """
    h, w = panel_bits.shape
    if h != 7:
        raise ValueError(f"Panel height must be 7, got {h}")
    # weights for rows y=0..6 become bit 1<<y
    weights = (1 << np.arange(7, dtype=np.uint8)).reshape(7, 1)
    # Broadcast multiply booleans by weights and sum per column
    vals = (panel_bits.astype(np.uint8) * weights).sum(axis=0) & 0x7F
    return vals.tobytes()


def encode_panel_message(panel_bits: np.ndarray, address: int, refresh: bool = False) -> bytes:
    """Encode a single panel message with given device address."""
    _h, w = panel_bits.shape
    cmd = _cmd_for_panel_width(w, refresh)
    payload = panel_bits_to_column_bytes(panel_bits)
    return bytes([0x80, cmd, address]) + payload + bytes([0x8F])


def encode_flush() -> bytes:
    """Encode a broadcast flush frame."""
    return bytes([0x80, 0x82, 0x8F])
