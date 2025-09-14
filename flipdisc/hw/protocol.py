"""Flipdots display protocol configuration and helpers.

Defines enums and a static mapping from data size + refresh mode to command bytes,
with a small facade bound to a DisplayConfig for convenient encoding.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np

from ..config import DisplayConfig
from .formats import (
    encode_flush as _encode_flush,
    encode_panel_message as _encode_panel_message,
    panel_bits_to_column_bytes as _panel_bits_to_column_bytes,
)
from .spec import (
    DataBytes,
    Refresh,
    ProtocolConfig,
    PROTOCOL_MAP,
    data_bytes_from_panel_size,
    get_protocol_config,
    supports_buffered_refresh,
)


# Mapping and helpers imported from spec.py


class Protocol:
    """High-level encoder bound to a DisplayConfig."""

    def __init__(self, cfg: DisplayConfig):
        self.cfg = cfg
        self.panel_w = cfg.panel_w
        self.panel_h = cfg.panel_h
        self._data_bytes = data_bytes_from_panel_size(self.panel_w, self.panel_h)
        self._supports_buffered = supports_buffered_refresh(self._data_bytes)

    @property
    def supports_buffered(self) -> bool:
        return self._supports_buffered

    def panel_payload(self, panel_bits: np.ndarray) -> bytes:
        return _panel_bits_to_column_bytes(panel_bits)

    def encode_panel(
        self, panel_bits: np.ndarray, address: int, refresh: bool | None = None
    ) -> bytes:
        # Default behavior: 7x7 -> instant, 14/28 -> buffered
        if refresh is None:
            refresh = not self.supports_buffered
        return _encode_panel_message(panel_bits, address=address, refresh=refresh)

    def encode_batch(
        self, panels_bits: Iterable[np.ndarray], address_base: int
    ) -> bytes:
        msgs: list[bytes] = []
        for idx, panel_bits in enumerate(panels_bits):
            msgs.append(self.encode_panel(panel_bits, address=address_base + idx))
        batch = b"".join(msgs)
        if self.supports_buffered:
            batch += _encode_flush()
        return batch

    def encode_flush(self) -> bytes:
        return _encode_flush()
