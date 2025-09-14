"""Hardware task - manages display timing and serial communication."""

import asyncio
import contextlib
import logging
from collections.abc import Callable

import numpy as np

from ..config import DisplayConfig
from ..core.types import Frame
from ..exceptions import FrameError, HardwareError
from ..hw.panel_map import split_canvas_bits_to_panels
from ..hw.protocol import Protocol
from ..serial_port import SerialPort, create_serial_port

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
        """Add frame to buffer if space available."""
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
        """Get next frame from buffer."""
        try:
            return await asyncio.wait_for(self.frames.get(), timeout=0.1)
        except TimeoutError:
            return None

    # Credits are derived from free slots; explicit counters removed.

    def get_status(self) -> dict:
        """Get buffer status information."""
        return {
            "size": self.frames.qsize(),
            "max_size": self.max_size,
            "enqueued": self.enqueued,
            "dropped": self.dropped,
            "utilization": self.frames.qsize() / self.max_size,
        }


class HardwareTask:
    """
    Main hardware task with proper error handling.

    This task owns the display timing and serial communication.
    It drains the frame buffer at the target refresh rate and
    provides credits for frame production.
    """

    def __init__(self, config: DisplayConfig):
        self.config = config
        self.serial_port: SerialPort = create_serial_port(config.serial)
        self.protocol = Protocol(config)
        self.buffer = FrameBuffer(config)
        self.running = False
        self.frame_interval = 1.0 / config.refresh_rate
        self._presented = 0
        self._lock = asyncio.Lock()
        self._last_frame_bits: np.ndarray | None = None

        # Credit callback for WorkerManager
        # Callback invoked to request N credits be issued to workers
        self.credit_callback: Callable[[int], None] | None = None

    def set_credit_callback(self, callback: Callable[[int], None] | None):
        """Set callback to be called when credits are available."""
        self.credit_callback = callback

    async def start(self):
        """Start the hardware task."""
        try:
            await self.serial_port.connect()
            self.running = True
            logger.info(f"Hardware task started at {self.config.refresh_rate}fps")

            loop = asyncio.get_running_loop()
            # Main display loop
            while self.running:
                start_time = loop.time()

                # Get next frame from buffer (at most one per tick)
                frame_obj = await self.buffer.get_frame()
                if frame_obj:
                    try:
                        # Segmented write: split by panels, encode per-protocol, then flush
                        panel_bits_list = split_canvas_bits_to_panels(
                            frame_obj.bits, self.config
                        )
                        addr_base = getattr(self.config, "address_base", 1)
                        batch = self.protocol.encode_batch(panel_bits_list, addr_base)
                        await self.serial_port.write_frame(batch)
                    except Exception as e:
                        logger.error(f"Failed to write frame: {e}")
                        # Continue running even if individual frame fails

                # After draining (or not), compute free slots and issue credits to keep buffer topped
                if self.credit_callback:
                    try:
                        free = self.buffer.max_size - self.buffer.frames.qsize()
                        if free > 0:
                            self.credit_callback(free)
                    except Exception as e:
                        logger.error(f"Credit callback error: {e}")

                # Maintain frame rate
                # Latency logging every N frames
                if frame_obj is not None:
                    self._presented += 1
                    if self._presented % 20 == 0 and frame_obj.produced_ts is not None:
                        latency_ms = (loop.time() - frame_obj.produced_ts) * 1000.0
                        logger.info(
                            f"frame seq={frame_obj.seq} latency_ms={latency_ms:.1f} buffer={self.buffer.frames.qsize()}/{self.buffer.max_size}"
                        )
                    # Keep the most recent frame for preview/UI
                    self._last_frame_bits = frame_obj.bits.copy()

                elapsed = loop.time() - start_time
                sleep_time = max(0, self.frame_interval - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except Exception as e:
            # Propagate with context; caller decides severity and recovery.
            raise HardwareError(f"Hardware task failed: {e}") from e
        finally:
            self.running = False

    async def stop(self):
        """Stop the hardware task."""
        self.running = False
        try:
            await self.serial_port.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting serial port: {e}")
        logger.info("Hardware task stopped")

    async def reconnect_serial(self) -> None:
        """Reconnect the serial port (for API control)."""
        with contextlib.suppress(Exception):
            await self.serial_port.disconnect()
        await self.serial_port.connect()

    async def set_refresh_rate(self, refresh_rate: float) -> None:
        """Atomically update refresh rate and ticker interval."""
        if refresh_rate <= 0:
            raise HardwareError("refresh_rate must be positive")
        async with self._lock:
            self.config.refresh_rate = refresh_rate
            self.frame_interval = 1.0 / refresh_rate

    async def display_frame(self, frame: Frame):
        """Add frame to display buffer."""
        return await self.buffer.add_frame(frame)

    def get_status(self) -> dict:
        """Get hardware task status."""
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
        """Return a copy of the most recently presented frame bits, if any."""
        if self._last_frame_bits is None:
            return None
        return self._last_frame_bits.copy()
