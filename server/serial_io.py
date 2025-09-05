from __future__ import annotations

import asyncio
from typing import Dict, List

from aioserial import AioSerial

from .config import Panel, SerialCfg
from .mapping import to_column_bytes


class SerialWriter:
    async def write_panels(
        self, panels: List[Panel], bits: Dict[str, bytes]
    ) -> None:  # pragma: no cover - interface
        return None

    async def close(self) -> None:  # pragma: no cover - interface
        return None


class StubWriter(SerialWriter):
    async def write_panels(self, panels: List[Panel], bits: Dict[str, bytes]) -> None:
        return None

    async def close(self) -> None:
        return None


class RealWriter(SerialWriter):
    def __init__(self, cfg: SerialCfg, instant: bool, interpanel_us: int = 0):
        self.cfg = cfg
        self.instant = instant
        self.interpanel_us = interpanel_us
        # Require AioSerial; configure parity/data/stop bits if provided
        parity_map = {
            "none": "N",
            "n": "N",
            "even": "E",
            "e": "E",
            "odd": "O",
            "o": "O",
        }
        parity = parity_map.get((cfg.parity or "none").lower(), "N")
        bytesize = cfg.data_bits or 8
        stopbits = 2 if cfg.stop_bits == 2 else 1
        self._aio = AioSerial(cfg.device, cfg.baud, bytesize=bytesize, parity=parity, stopbits=stopbits)

    async def write_panels(self, panels: List[Panel], bits: Dict[str, bytes]) -> None:
        for p in panels:
            b = bits.get(p.id)
            if not b:
                continue
            cols = to_column_bytes(b, p.size.w, p.size.h)
            msg = self._build_msg(p, cols)
            await self._aio.write_async(msg)
            if self.interpanel_us > 0:
                await asyncio.sleep(self.interpanel_us / 1_000_000.0)

    def _build_msg(self, p: Panel, data: bytes) -> bytes:
        # cfg byte mapping mirrors original Driver CFG_MAP
        msg_len = len(data)
        if self.instant:
            cfg = _CFG_MAP_INSTANT.get(msg_len, 0x83)
        else:
            cfg = _CFG_MAP_NON_INSTANT.get(msg_len, 0x84)
        addr = p.address & 0xFF
        return bytes([0x80, cfg, addr]) + data + bytes([0x8F])

    async def close(self) -> None:
        try:
            self._aio.close()
        except Exception:
            pass


# CFG mapping tables for clarity
_CFG_MAP_INSTANT = {
    0: 0x82,   # config only (rarely used)
    7: 0x87,
    14: 0x92,
    28: 0x83,
}

_CFG_MAP_NON_INSTANT = {
    14: 0x93,
    28: 0x84,
}
