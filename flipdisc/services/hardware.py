"""Hardware task - manages display timing and serial communication."""

import asyncio
import logging
import time
from collections.abc import Callable

import numpy as np

from ..config import DisplayConfig
from ..core.types import Frame
from ..exceptions import FrameError, HardwareError
from ..hw.formats import encode_panel_message
from ..hw.panel_map import split_canvas_bits_to_panels
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
        self.credits = max_size  # Available credits for frame production
        self.credits_lock = asyncio.Lock()
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
            frame = await asyncio.wait_for(self.frames.get(), timeout=0.1)
            # Return a credit when we consume a frame
            async with self.credits_lock:
                self.credits = min(self.credits + 1, self.max_size)
            return frame
        except TimeoutError:
            return None

    async def get_credits(self) -> int:
        """Get available credits for frame production."""
        async with self.credits_lock:
            return self.credits

    async def consume_credit(self) -> bool:
        """Consume a credit for frame production."""
        async with self.credits_lock:
            if self.credits > 0:
                self.credits -= 1
                return True
            return False

    def get_status(self) -> dict:
        """Get buffer status information."""
        return {
            "size": self.frames.qsize(),
            "max_size": self.max_size,
            "credits": self.credits,
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
        self.buffer = FrameBuffer(config)
        self.running = False
        self.frame_interval = 1.0 / config.refresh_rate

        # Credit callback for WorkerManager
        # Callback invoked to request N credits be issued to workers
        self.credit_callback: Callable[[int], None] | None = None

    def set_credit_callback(self, callback: Callable[[int], None]):
        """Set callback to be called when credits are available."""
        self.credit_callback = callback

    async def start(self):
        """Start the hardware task."""
        try:
            await self.serial_port.connect()
            self.running = True
            logger.info(f"Hardware task started at {self.config.refresh_rate}fps")

            # Main display loop
            while self.running:
                start_time = time.monotonic()

                # Get next frame from buffer (at most one per tick)
                frame_obj = await self.buffer.get_frame()
                if frame_obj:
                    try:
                        # Segmented write: split by panels, encode per-protocol, then flush
                        panel_bits_list = split_canvas_bits_to_panels(frame_obj.bits, self.config)
                        addr_base = getattr(self.config, "address_base", 1)
                        for idx, panel_bits in enumerate(panel_bits_list):
                            address = addr_base + idx
                            msg = encode_panel_message(panel_bits, address, refresh=False)
                            await self.serial_port.write_frame(msg)
                        await self.serial_port.write_flush()
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
                elapsed = time.monotonic() - start_time
                sleep_time = max(0, self.frame_interval - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except Exception as e:
            logger.error(f"Hardware task failed: {e}")
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
        try:
            await self.serial_port.disconnect()
        except Exception:
            pass
        await self.serial_port.connect()

    async def display_frame(self, frame: Frame):
        """Add frame to display buffer."""
        return await self.buffer.add_frame(frame)

    async def get_credits(self) -> int:
        """Get available credits for frame production."""
        return await self.buffer.get_credits()

    def get_status(self) -> dict:
        """Get hardware task status."""
        return {
            "running": self.running,
            "connected": self.serial_port.is_connected(),
            "buffer": self.buffer.get_status(),
            "config": {
                "width": self.config.width,
                "height": self.config.height,
                "refresh_rate": self.config.refresh_rate,
                "serial_port": self.config.serial.port,
                "mock_serial": self.config.serial.mock,
            },
        }
