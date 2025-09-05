from __future__ import annotations

from typing import Dict

import numpy as np

from .config import DisplayConfig


def update_panels(canvas_bits: bytes, canvas_w: int, canvas_h: int, cfg: DisplayConfig) -> Dict[str, bytes]:
    # Unpack canvas bits -> boolean array [H, W]
    stride = (canvas_w + 7) // 8
    canvas = (
        np.unpackbits(np.frombuffer(canvas_bits, dtype=np.uint8).reshape((canvas_h, stride)), axis=1, bitorder="big")
        [:, :canvas_w]
        .astype(bool)
    )

    out: Dict[str, bytes] = {}
    for p in cfg.panels:
        x0, y0 = p.origin.x, p.origin.y
        w, h = p.size.w, p.size.h
        sub = canvas[y0 : y0 + h, x0 : x0 + w]
        orientation = (p.orientation or "normal").lower()
        sub = (
            np.rot90(sub, k=3) if orientation == "rot90" else
            np.rot90(sub, k=2) if orientation == "rot180" else
            np.rot90(sub, k=1) if orientation == "rot270" else
            np.fliplr(sub)      if orientation == "fliph"  else
            np.flipud(sub)      if orientation == "flipv"  else
            sub
        )
        # Pad width to multiple of 8 columns, then pack MSB-first per row
        pad_cols = (-w) % 8
        sub_pad = (np.pad(sub, ((0, 0), (0, pad_cols)), mode="constant", constant_values=False) if pad_cols else sub)
        out[p.id] = np.packbits(sub_pad, axis=1, bitorder="big").tobytes()
    return out


def to_column_bytes(packed: bytes, w: int, h: int) -> bytes:
    # Unpack panel-local packed rows to [H, W] then fold each column into a byte (top bit first)
    stride = (w + 7) // 8
    bits = (
        np.unpackbits(np.frombuffer(packed, dtype=np.uint8).reshape((h, stride)), axis=1, bitorder="big")[:, :w]
        .astype(np.uint8)
    )
    weights = 1 << np.arange(h - 1, -1, -1, dtype=np.uint16)
    vals = bits.T.dot(weights).clip(0, 255).astype(np.uint8)
    return vals.tobytes()
