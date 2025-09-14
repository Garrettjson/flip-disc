"""Protocol encoder for Flipdots panels based on PROTOCOL.md.

Frame format (general): 0x80 <CMD> <ADDR> <DATA...> 0x8F

Flush: 0x80 0x82 0x8F

Data for panel frames: width bytes, one per column. Each byte packs 7 bits
for a 7-pixel-tall column: bit0=top pixel, bit6=bottom pixel, bit7 must be 0.
"""

import numpy as np
from .constants import START_BYTE, END_BYTE, PANEL_HEIGHT, Command
from .spec import DataBytes, Refresh, data_bytes_from_panel_size, get_protocol_config


def _cmd_for_panel_width(panel_w: int, refresh: bool) -> int:
    """Return command byte using the protocol mapping (no magic numbers)."""
    data_bytes = data_bytes_from_panel_size(panel_w, PANEL_HEIGHT)
    mode = Refresh.INSTANT if refresh else Refresh.BUFFER
    return get_protocol_config(data_bytes, mode).command_byte


def panel_bits_to_column_bytes(panel_bits: np.ndarray) -> bytes:
    """Pack panel boolean image (H=7) to column bytes using NumPy packbits.

    - LSB=top pixel, bit7=0 per spec.
    - Returns W bytes; W in {7, 14, 28}.
    """
    h, _ = panel_bits.shape
    if h != PANEL_HEIGHT:
        raise ValueError(f"Panel height must be {PANEL_HEIGHT}, got {h}")
    # Pack along the row axis so each column becomes one byte.
    # bitorder='little' ensures first bit (top pixel y=0) maps to LSB (bit0).
    packed = np.packbits(panel_bits.astype(np.uint8), axis=0, bitorder="little")
    # Shape is (1, w); flatten to (w,) and return bytes. Bit7 is zero due to 7 inputs.
    return packed.reshape(-1).tobytes()


def encode_panel_message(
    panel_bits: np.ndarray, address: int, refresh: bool = False
) -> bytes:
    """Encode a single panel message with given device address."""
    _, w = panel_bits.shape
    cmd = _cmd_for_panel_width(w, refresh)
    payload = panel_bits_to_column_bytes(panel_bits)
    return bytes([START_BYTE, cmd, address]) + payload + bytes([END_BYTE])


def encode_flush() -> bytes:
    """Encode a broadcast flush frame."""
    return bytes([START_BYTE, int(Command.FLUSH), END_BYTE])
