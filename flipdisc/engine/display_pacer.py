"""DisplayPacer - manages display timing and serial communication."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable

import numpy as np

from ..config import DisplayConfig
from ..core.exceptions import FrameError, HardwareError
from ..core.types import Frame
from ..hardware.panel_map import split_canvas_bits_to_panels
from ..hardware.protocol import ProtocolEncoder
from ..hardware.transport.serial import SerialTransport, create_serial_transport

logger = logging.getLogger(__name__)


class FrameBuffer:
    """Frame buffer with backpressure and proper error handling."""

    def __init__(self, config: DisplayConfig, max_size: int | None = None):
        self.config = config
        if max_size is None:
            max_size = int(config.refresh_rate * config.buffer_duration)
        self.max_size = max_size
        self.frames: asyncio.Queue[Frame] = asyncio.Queue(maxsize=max_size)
        self.enqueued = 0
        self.dropped = 0

    async def add_frame(self, frame: Frame) -> bool:
        if not isinstance(frame, Frame):
            raise FrameError(f"Expected Frame object, got {type(frame)}")
        bits = frame.bits
        if not isinstance(bits, np.ndarray) or bits.dtype != bool or bits.ndim != 2:
            raise FrameError("Frame.bits must be 2D numpy bool array")
        h, w = bits.shape
        if (h, w) != (self.config.height, self.config.width):
            raise FrameError(
                f"Frame shape mismatch: expected {(self.config.height, self.config.width)}, got {(h, w)}"
            )

        try:
            self.frames.put_nowait(frame)
            self.enqueued += 1
            logger.debug(
                f"Added frame to buffer ({self.frames.qsize()}/{self.max_size})"
            )
            return True
        except asyncio.QueueFull:
            logger.warning("Frame buffer full, dropping frame")
            self.dropped += 1
            return False

    async def get_frame(self) -> Frame | None:
        try:
            return await asyncio.wait_for(self.frames.get(), timeout=0.1)
        except TimeoutError:
            return None

    def get_status(self) -> dict:
        return {
            "size": self.frames.qsize(),
            "max_size": self.max_size,
            "enqueued": self.enqueued,
            "dropped": self.dropped,
            "utilization": self.frames.qsize() / self.max_size,
        }


class DisplayPacer:
    """Main display pacing task and serial I/O owner."""

    def __init__(self, config: DisplayConfig):
        self.config = config
        self.serial_port: SerialTransport = create_serial_transport(config.serial)
        self.protocol = ProtocolEncoder(config)
        self.buffer = FrameBuffer(config)
        self.running = False
        self.frame_interval = 1.0 / config.refresh_rate
        self._presented = 0
        self._lock = asyncio.Lock()
        self._last_frame_bits: np.ndarray | None = None

        # Credit callback for worker pool
        self.credit_callback: Callable[[int], None] | None = None

    def set_credit_callback(self, callback: Callable[[int], None] | None) -> None:
        self.credit_callback = callback

    async def start(self) -> None:
        try:
            await self.serial_port.connect()
            self.running = True
            logger.info(f"DisplayPacer started at {self.config.refresh_rate}fps")

            loop = asyncio.get_running_loop()
            while self.running:
                start_time = loop.time()

                frame_obj = await self.buffer.get_frame()
                if frame_obj:
                    try:
                        panel_bits_list = split_canvas_bits_to_panels(
                            frame_obj.bits, self.config
                        )
                        addr_base = getattr(self.config, "address_base", 1)
                        batch = self.protocol.encode_batch(panel_bits_list, addr_base)
                        await self.serial_port.write_frames([batch])
                    except Exception as e:
                        logger.error(f"Failed to write frame: {e}")

                if self.credit_callback:
                    try:
                        free = self.buffer.max_size - self.buffer.frames.qsize()
                        if free > 0:
                            self.credit_callback(free)
                    except Exception as e:
                        logger.error(f"Credit callback error: {e}")

                if frame_obj is not None:
                    self._presented += 1
                    if self._presented % 20 == 0 and frame_obj.produced_ts is not None:
                        latency_ms = (loop.time() - frame_obj.produced_ts) * 1000.0
                        logger.info(
                            f"frame seq={frame_obj.seq} latency_ms={latency_ms:.1f} buffer={self.buffer.frames.qsize()}/{self.buffer.max_size}"
                        )
                    self._last_frame_bits = frame_obj.bits.copy()

                elapsed = loop.time() - start_time
                sleep_time = max(0, self.frame_interval - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except Exception as e:
            raise HardwareError(f"DisplayPacer failed: {e}") from e
        finally:
            self.running = False

    async def stop(self) -> None:
        self.running = False
        try:
            await self.serial_port.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting serial port: {e}")
        logger.info("DisplayPacer stopped")

    async def reconnect_serial(self) -> None:
        with contextlib.suppress(Exception):
            await self.serial_port.disconnect()
        await self.serial_port.connect()

    async def set_refresh_rate(self, refresh_rate: float) -> None:
        if refresh_rate <= 0:
            raise HardwareError("refresh_rate must be positive")
        async with self._lock:
            self.config.refresh_rate = refresh_rate
            self.frame_interval = 1.0 / refresh_rate

    async def display_frame(self, frame: Frame) -> bool:
        return await self.buffer.add_frame(frame)

    def get_status(self) -> dict:
        return {
            "running": self.running,
            "connected": self.serial_port.is_connected(),
            "buffer": {
                **self.buffer.get_status(),
                "free": self.buffer.max_size - self.buffer.frames.qsize(),
            },
            "config": {
                "width": self.config.width,
                "height": self.config.height,
                "refresh_rate": self.config.refresh_rate,
                "serial_port": self.config.serial.port,
                "mock_serial": self.config.serial.mock,
            },
            "frames_presented": self._presented,
        }

    def get_last_frame_bits(self) -> np.ndarray | None:
        if self._last_frame_bits is None:
            return None
        return self._last_frame_bits.copy()
