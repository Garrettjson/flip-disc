"""DisplayPipeline: orchestrates the generator/postproc pipeline and presenter.

Creates two SPSC rings (raw float32 and ready bool), spawns two processes, and
owns an async presenter that consumes ready frames at the configured refresh
rate, encodes them, writes to serial, and broadcasts preview frames.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import multiprocessing as mp
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from flipdisc.config import DisplayConfig
from flipdisc.core.exceptions import HardwareError
from flipdisc.hardware.panel_map import split_canvas_bits_to_panels
from flipdisc.hardware.protocol import ProtocolEncoder
from flipdisc.hardware.transport.serial import SerialTransport, create_serial_transport

from .processes.generator import generator_main
from .processes.postproc import postproc_main
from .shared_ring import SPSCSharedRing

logger = logging.getLogger(__name__)


@dataclass
class PipelineStatus:
    running: bool
    playing: bool
    frames_presented: int
    raw_ring: dict[str, Any]
    ready_ring: dict[str, Any]


class DisplayPipeline:
    def __init__(self, cfg: DisplayConfig) -> None:
        self.cfg = cfg
        self.frame_interval = 1.0 / cfg.refresh_rate
        self.serial: SerialTransport = create_serial_transport(cfg.serial)
        self._ctx = mp.get_context()
        self.encoder = ProtocolEncoder(cfg)

        # Shared events
        self.running_event = self._ctx.Event()
        self.reset_event = self._ctx.Event()

        # Rings
        ready_capacity = max(1, int(cfg.refresh_rate * cfg.buffer_duration))
        raw_capacity = ready_capacity + 1
        (
            self.raw_ring,
            self.raw_meta,
            self.raw_head,
            self.raw_tail,
            self.raw_free,
            self.raw_items,
        ) = SPSCSharedRing.create(raw_capacity, cfg.height, cfg.width, "float32")
        (
            self.ready_ring,
            self.ready_meta,
            self.ready_head,
            self.ready_tail,
            self.ready_free,
            self.ready_items,
        ) = SPSCSharedRing.create(ready_capacity, cfg.height, cfg.width, "bool")

        # Processes
        self._gen_proc: mp.Process | None = None
        self._pp_proc: mp.Process | None = None

        # Presenter task
        self._presenter_task: asyncio.Task | None = None
        self._presented = 0
        self._running = False
        self._playing = False

        # Last frame storage + callback
        self._last_frame: np.ndarray | None = None
        self._preview_cb: Callable[[np.ndarray], None] | None = None

    def set_preview_callback(self, cb: Callable[[np.ndarray], None] | None) -> None:
        self._preview_cb = cb

    @property
    def running(self) -> bool:
        return self._running

    @property
    def playing(self) -> bool:
        return self._playing

    async def start(
        self, animation: str = "bouncing_dot", params: dict[str, Any] | None = None
    ) -> None:
        if params is None:
            params = {}
        await self.serial.connect()
        self._running = True

        # Spawn generator and postproc processes
        self._gen_proc = self._ctx.Process(
            target=generator_main,
            args=(
                self.raw_meta,
                self.raw_head,
                self.raw_tail,
                self.raw_free,
                self.raw_items,
                self.running_event,
                self._ctx.Event(),  # reload_event placeholder
                self.reset_event,
                self.cfg.width,
                self.cfg.height,
                animation,
                params,
            ),
            name="GeneratorProcess",
        )
        # Workaround: since generator_main expects get_config callable, create a thin wrapper function
        # that reconstructs config. We'll instead modify generator_main later. For now, start paused.

        # Start post-processor process
        self._pp_proc = self._ctx.Process(
            target=postproc_main,
            args=(
                self.raw_meta,
                self.raw_head,
                self.raw_tail,
                self.raw_free,
                self.raw_items,
                self.ready_meta,
                self.ready_head,
                self.ready_tail,
                self.ready_free,
                self.ready_items,
                self.running_event,
            ),
            name="PostProcessorProcess",
        )

        # Start processes
        self._gen_proc.start()
        self._pp_proc.start()

        # Presenter task
        self._presenter_task = asyncio.create_task(self._present_loop())

    async def stop(self) -> None:
        self._running = False
        self.running_event.clear()
        if self._presenter_task:
            self._presenter_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._presenter_task
        # Stop processes
        for proc in (self._gen_proc, self._pp_proc):
            if proc and proc.is_alive():
                proc.terminate()
                proc.join(timeout=1.0)
        self._gen_proc = None
        self._pp_proc = None

        # Close serial and rings
        with contextlib.suppress(Exception):
            await self.serial.disconnect()
        self.raw_ring.close()
        self.ready_ring.close()
        # Owner should unlink
        with contextlib.suppress(Exception):
            self.raw_ring.unlink()
        with contextlib.suppress(Exception):
            self.ready_ring.unlink()

    async def play(self) -> None:
        self._playing = True
        self.running_event.set()

    async def pause(self) -> None:
        self._playing = False
        self.running_event.clear()

    async def reset(self) -> None:
        self.reset_event.set()

    def get_status(self) -> PipelineStatus:
        return PipelineStatus(
            running=self._running,
            playing=self._playing,
            frames_presented=self._presented,
            raw_ring=self.raw_ring.get_status(),
            ready_ring=self.ready_ring.get_status(),
        )

    def get_last_frame_bits(self) -> np.ndarray | None:
        return self._last_frame

    async def _present_loop(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            while self._running:
                start = loop.time()
                # Try acquire a ready frame within this tick interval
                remaining = max(0.0, self.frame_interval * 0.9)
                _, view = self.ready_ring.consumer_acquire_timeout(remaining)
                if view is not None:
                    try:
                        panel_bits_list = split_canvas_bits_to_panels(view, self.cfg)
                        addr_base = getattr(self.cfg, "address_base", 1)
                        batch = self.encoder.encode_batch(panel_bits_list, addr_base)
                        await self.serial.write_frames([batch])
                        # Store last frame and broadcast preview
                        self._last_frame = view.copy()
                        if self._preview_cb is not None:
                            try:
                                self._preview_cb(view)
                            except Exception:
                                self._preview_cb = None
                        self._presented += 1
                    finally:
                        self.ready_ring.consumer_release()

                # Sleep remainder of tick
                elapsed = loop.time() - start
                sleep_time = max(0.0, self.frame_interval - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            raise HardwareError(f"Presenter failed: {e}") from e

    # --- Control helpers for API ----------------------------------------

    async def set_refresh_rate(self, new_fps: float) -> None:
        if new_fps <= 0:
            raise HardwareError("refresh_rate must be positive")
        self.cfg.refresh_rate = new_fps
        self.frame_interval = 1.0 / new_fps

    async def reconnect_serial(self) -> None:
        with contextlib.suppress(Exception):
            await self.serial.disconnect()
        await self.serial.connect()

    async def set_animation(
        self, name: str, params: dict[str, Any] | None = None
    ) -> None:
        """(Re)start the generator process with a new animation.

        Keeps the rings and presenter; only restarts the generator process.
        """
        if params is None:
            params = {}
        # Stop current generator
        if self._gen_proc and self._gen_proc.is_alive():
            self._gen_proc.terminate()
            self._gen_proc.join(timeout=1.0)
        # Start a new generator with provided animation
        self._gen_proc = self._ctx.Process(
            target=generator_main,
            args=(
                self.raw_meta,
                self.raw_head,
                self.raw_tail,
                self.raw_free,
                self.raw_items,
                self.running_event,
                self._ctx.Event(),  # reload placeholder
                self.reset_event,
                self.cfg.width,
                self.cfg.height,
                name,
                params,
            ),
            name="GeneratorProcess",
        )
        self._gen_proc.start()
