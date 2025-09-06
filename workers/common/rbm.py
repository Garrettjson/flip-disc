from __future__ import annotations

import math
import struct
from typing import Iterable, List


def pack_bitmap_1bit(rows: Iterable[Iterable[int]], width: int, height: int) -> bytes:
    """Pack a 2D array of 0/1 ints into MSB-first row-major bytes.

    rows: iterable of rows, each an iterable of 0/1 values, length=height
    width, height: dimensions of the logical canvas
    """
    stride = (width + 7) // 8
    out = bytearray(height * stride)
    y = 0
    for row in rows:
        x = 0
        byte_idx = y * stride
        current = 0
        bitpos = 7
        for v in row:
            if v:
                current |= 1 << bitpos
            bitpos -= 1
            x += 1
            if bitpos < 0:
                out[byte_idx] = current
                byte_idx += 1
                current = 0
                bitpos = 7
            if x >= width:
                break
        if bitpos != 7:
            out[byte_idx] = current
        y += 1
        if y >= height:
            break
    return bytes(out)


def encode_rbm(
    frame_bits: bytes,
    width: int,
    height: int,
    seq: int = 0,
    frame_duration_ms: int = 0,
    flags: int = 0,
) -> bytes:
    """Encode RBM header + payload (see protocol/rbm_spec.md)."""
    magic = b"RB"
    version = 1
    header = struct.pack(
        ">2sBBHHIHH",
        magic,
        version,
        flags,
        width,
        height,
        seq & 0xFFFFFFFF,
        frame_duration_ms & 0xFFFF,
        0,  # reserved
    )
    return header + frame_bits
