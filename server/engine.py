from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional

from .config import DisplayConfig
from .mapping import update_panels
from .serial_io import SerialWriter


@dataclass
class FrameItem:
    bits: bytes
    seq: int
    duration_ms: int


class ServerState:
    """Holds display state, ring buffer, and the paced writer.

    - Maintains an authoritative frame buffer (packed MSB-first rows)
    - Derives per-panel bitmaps on each writer tick
    - Writes to serial via the provided SerialWriter implementation
    """

    MAX_FPS = 30  # absolute ceiling enforced by server pacing

    def __init__(self, cfg: DisplayConfig, fps: int, buffer_ms: int, frame_gap_ms: int, serial_writer: SerialWriter):
        self.cfg = cfg
        self.width = cfg.canvas.width
        self.height = cfg.canvas.height
        self.stride = (self.width + 7) // 8
        self.frame_bits: bytes = bytes(self.height * self.stride)
        self.panel_bits: Dict[str, bytes] = {}

        # pacing
        # enforce server-side max FPS
        self.min_interval = 1.0 / float(self.MAX_FPS)
        self.default_interval = max(1.0 / max(1, fps), self.min_interval)
        cap = max(1, int((buffer_ms / 1000.0) / self.default_interval))
        self.buf: Deque[FrameItem] = deque(maxlen=cap)
        self.frame_gap_ms = max(0, frame_gap_ms)

        # stats
        self.recv_count = 0
        self.write_count = 0
        self.last_write_ms = 0.0
        self.last_interval_ms = 0.0
        self.last_seq_ack: int = 0

        self.serial = serial_writer
        self._writer_task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._writer_task is None:
            self._writer_task = asyncio.create_task(self._writer_loop())

    async def stop(self) -> None:
        if self._writer_task is not None:
            self._writer_task.cancel()
            try:
                await self._writer_task
            except asyncio.CancelledError:
                pass
            self._writer_task = None
        try:
            await self.serial.close()
        except Exception:
            pass

    async def _writer_loop(self) -> None:
        prev_tick = 0.0
        interval = self.default_interval
        try:
            while True:
                t0 = time.perf_counter()
                if self.buf:
                    it = self.buf.popleft()
                    self.frame_bits = it.bits
                    self.panel_bits = update_panels(self.frame_bits, self.width, self.height, self.cfg)
                    interval = (it.duration_ms / 1000.0) if it.duration_ms > 0 else self.default_interval
                    interval = max(interval, self.min_interval)
                t_write0 = time.perf_counter()
                await self.serial.write_panels(self.cfg.panels, self.panel_bits)
                t_write1 = time.perf_counter()
                self.last_write_ms = (t_write1 - t_write0) * 1000.0
                if prev_tick != 0.0:
                    self.last_interval_ms = (t0 - prev_tick) * 1000.0
                prev_tick = t0
                self.write_count += 1
                eff = max(interval, self.frame_gap_ms / 1000.0)
                await asyncio.sleep(eff)
        except asyncio.CancelledError:
            return
