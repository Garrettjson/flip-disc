from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional
import numpy as np

from serial import SerialException
from aioserial import AioSerial

from .config import DisplayConfig
from .protocol_config import Refresh, get_protocol_config, FLUSH_COMMAND

logger = logging.getLogger(__name__)


class SerialConnectError(Exception):
    """Raised when serial hardware cannot be initialized."""

    pass


class SerialWriteError(Exception):
    """Raised when writing data to a panel fails."""

    pass


class SerialFlushError(Exception):
    """Raised when flush command to panels fails."""

    pass


class SerialWriter(ABC):
    """
    Abstract base class for serial writers.
    Defines the interface for writing data to flip disc panels.
    """

    @abstractmethod
    async def write_panel_data(self, panel_data: Dict[int, np.ndarray]) -> None:
        """
        Write data to multiple panels.

        Args:
            panel_data: Dict mapping panel addresses to numpy arrays of pixel data

        Raises:
            SerialWriteError: If writing to panels fails
        """
        pass

    @abstractmethod
    async def write_single_panel(self, address: int, data: np.ndarray) -> None:
        """
        Write data to a single panel.

        Args:
            address: Panel RS-485 address
            data: Numpy array of pixel data (height x width)

        Raises:
            SerialWriteError: If writing to panel fails
        """
        pass

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to serial interface.

        Returns:
            bool: True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close serial connection."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connection is active."""
        pass


class MockWriter(SerialWriter):
    """
    Mock serial writer for development and testing.
    Logs what would be sent to panels instead of actual serial communication.
    """

    def __init__(self, display_config: DisplayConfig):
        self.config = display_config
        self.connected = False
        self.write_count = 0

        # Create panel lookup
        self._panels_by_address = {
            panel.address: panel for panel in self.config.enabled_panels
        }

        self.logger = logging.getLogger(f"{__name__}.mock")

    async def connect(self) -> bool:
        """Mock connection - always succeeds."""
        await asyncio.sleep(0.1)  # Simulate connection delay
        self.connected = True

        self.logger.info(
            f"MOCK: Connected to {self.config.serial.port} at {self.config.serial.baudrate} baud"
        )
        self.logger.info(f"MOCK: {self.config.panel_count} panels configured")

        for panel in self.config.enabled_panels:
            self.logger.info(
                f"MOCK: Panel '{panel.id}' - address {panel.address}, size {panel.size.w}x{panel.size.h}"
            )

        return True

    async def disconnect(self) -> None:
        """Mock disconnection."""
        if self.connected:
            await asyncio.sleep(0.05)
            self.connected = False
            self.logger.info(f"MOCK: Disconnected (sent {self.write_count} messages)")

    def is_connected(self) -> bool:
        """Check mock connection status."""
        return self.connected

    async def write_single_panel(self, address: int, data: np.ndarray) -> None:
        """Mock single panel write with detailed logging."""
        if not self.connected:
            raise SerialWriteError("MOCK: Not connected - cannot write")

        panel = self._panels_by_address.get(address)
        if not panel:
            raise SerialWriteError(f"MOCK: Unknown panel address {address}")

        # Validate data shape
        expected_shape = (panel.size.h, panel.size.w)
        if data.shape != expected_shape:
            raise SerialWriteError(
                f"MOCK: Panel {panel.id} data shape {data.shape} != expected {expected_shape}"
            )

        # Simulate write timing
        data_bytes = (panel.size.w * panel.size.h + 7) // 8
        message_bytes = 5 + data_bytes  # HEADER + CFG + ADDR + DATA + EOT
        write_time = (
            message_bytes * 10 / self.config.serial.baudrate
        )  # 10 bits per byte

        await asyncio.sleep(write_time)

        # Log the write
        pixels_on = np.sum(data)
        total_pixels = data.size

        self.logger.info(
            f"MOCK: Panel '{panel.id}' (addr {address}) - {pixels_on}/{total_pixels} pixels ({pixels_on/total_pixels*100:.1f}%)"
        )
        self.logger.debug(
            f"MOCK: Simulated {write_time*1000:.1f}ms write time for {message_bytes} bytes"
        )

        self.write_count += 1

    async def write_panel_data(self, panel_data: Dict[int, np.ndarray]) -> None:
        """Mock multi-panel write with buffered strategy simulation."""
        if not self.connected:
            raise SerialWriteError("MOCK: Not connected - cannot write panel data")

        panel_count = len(panel_data)
        use_buffered = panel_count > 1

        if use_buffered:
            self.logger.info(
                f"MOCK: Buffered write to {panel_count} panels (prevents visual artifacts)"
            )
        else:
            self.logger.info(f"MOCK: Direct write to {panel_count} panel")

        for address, data in panel_data.items():
            await self.write_single_panel(address, data)

        # Simulate flush command for multi-panel updates
        if use_buffered:
            await asyncio.sleep(0.001)  # Simulate flush command timing
            self.logger.info(
                "MOCK: Flush command sent - all panels refresh simultaneously"
            )

        self.logger.info("MOCK: All panel writes completed successfully")


class HardwareWriter(SerialWriter):
    """
    Real serial writer for actual hardware communication.
    Uses aioserial for async RS-485 communication with flip disc panels.
    """

    # Protocol constants from manufacturer documentation
    HEADER = 0x80
    EOT = 0x8F

    def __init__(
        self,
        display_config: DisplayConfig,
        interpanel_delay_us: int = 0,
    ):
        self.config = display_config
        self.interpanel_delay = interpanel_delay_us / 1_000_000.0  # Convert to seconds
        self._serial: AioSerial | None = None

        # prevents connect/disconnect races
        self._io_lock = asyncio.Lock()
        self._tx_lock = asyncio.Lock()

        # Create panel lookup
        self._panels_by_address = {
            panel.address: panel for panel in self.config.enabled_panels
        }

        self.logger = logging.getLogger(f"{__name__}.hardware")

        # Get panel data bytes from config (already validated as DataBytes enum)
        self.panel_data_bytes = self.config.panel_type

    @property
    def serial(self) -> AioSerial:
        if self._serial is None:
            raise SerialConnectError("HardwareWriter not connected")
        return self._serial

    async def connect(self):
        """Connect to real serial hardware."""
        async with self._io_lock:
            if self._serial is not None:
                return  # already connected

            try:
                # Configure serial based on config
                self._serial = AioSerial(
                    self.config.serial.port,
                    self.config.serial.baudrate,
                    timeout=self.config.serial.timeout,
                )

                self.logger.info(
                    f"Connected to {self.config.serial.port} at {self.config.serial.baudrate} baud"
                )
                self.logger.info(
                    f"interpanel delay: {self.interpanel_delay*1000:.1f}ms"
                )

            except (SerialException, OSError, ValueError) as e:
                raise SerialConnectError(
                    f"Failed to connect to serial port {self.config.serial.port}: {e}"
                )

    async def disconnect(self) -> None:
        """Disconnect from serial hardware."""
        async with self._io_lock:
            # clear first to block new users
            s, self._serial = self._serial, None
        if s is None:
            return
        try:
            s.close()
            self.logger.info("Serial connection closed")
        except Exception as e:
            self.logger.warning(f"Error closing serial connection: {e}")
        finally:
            s = None

    def is_connected(self) -> bool:
        """Check if serial connection is active."""
        return self._serial is not None and self._serial.is_open

    def _pack_panel_data(self, data: np.ndarray) -> bytes:
        """Pack numpy array into bytes for transmission."""
        """Pack numpy array into bytes for transmission (8 pixels per byte, MSB first)."""
        flat = data.flatten()
        out = bytearray((len(flat) + 7) // 8)
        for i, bit in enumerate(flat):
            if bit:
                byte_index, bit_pos = divmod(i, 8)
                out[byte_index] |= 1 << (7 - bit_pos)
        return bytes(out)

    def _build_message(self, panel, data: bytes, *, buffered: bool) -> bytes:
        """Build complete serial message for panel."""
        # Get protocol configuration based on panel type and refresh mode
        refresh_mode = Refresh.BUFFER if buffered else Refresh.INSTANT
        protocol_config = get_protocol_config(self.panel_data_bytes, refresh_mode)

        # Validate data length matches expected
        if len(data) != protocol_config.data_bytes:
            raise SerialWriteError(
                f"Panel '{panel.id}' data length {len(data)} != expected {protocol_config.data_bytes} "
                f"for {self.panel_data_bytes} panels"
            )

        # Build message: HEADER + CFG + ADDRESS + DATA + EOT
        message = (
            bytes([self.HEADER, protocol_config.command_byte, panel.address & 0xFF])
            + data
            + bytes([self.EOT])
        )

        return message

    def _prepare_panel_message(
        self, address: int, data: np.ndarray, *, buffered: bool
    ) -> bytes:
        """Validate shape, pack pixels, and build a message for a given panel."""
        panel = self._panels_by_address.get(address)
        if not panel:
            raise SerialWriteError(f"Unknown panel address {address}")

        expected_shape = (panel.size.h, panel.size.w)
        if data.shape != expected_shape:
            raise SerialWriteError(
                f"Panel {panel.id} data shape {data.shape} != expected {expected_shape}"
            )
        packed = self._pack_panel_data(data)
        return self._build_message(panel, packed, buffered=buffered)

    async def _send_bytes_unlocked(self, payload: bytes) -> int:
        """Low-level send. Caller must hold _tx_lock."""
        bytes_written = await self.serial.write_async(payload)
        return bytes_written

    async def write_single_panel(self, address: int, data: np.ndarray) -> None:
        """
        Write a single panel with **unbuffered** (immediate) update.
        Safe for concurrent callers (serialized via _tx_lock).
        """
        if not self.is_connected():
            raise SerialWriteError("Not connected to serial port")

        # Prepare outside the lock
        message = self._prepare_panel_message(address, data, buffered=False)

        try:
            async with self._tx_lock:
                bytes_written = await self._send_bytes_unlocked(message)

                if bytes_written != len(message):
                    raise SerialWriteError(
                        f"Panel addr {address} - wrote {bytes_written}/{len(message)} bytes"
                    )
            self.logger.debug(
                "Panel addr %d immediate write ok (%d bytes)", address, len(message)
            )

        except (SerialException, OSError, ValueError) as e:
            self.logger.debug("Failed to write to panel %s", address, exc_info=True)
            raise SerialWriteError(f"Failed to write to panel {address}: {e}") from e

    async def write_panel_data(self, panel_data: Dict[int, np.ndarray]) -> None:
        """
        Buffered multi-panel write: buffer all panels, then flush once.
        Holds the TX lock for the entire batch to prevent interleaving.
        """
        if not self.is_connected():
            raise SerialWriteError("Not connected to serial port")

        # Build all messages first (validate shapes, pack) to minimize lock time
        try:
            messages = [
                self._prepare_panel_message(addr, data, buffered=True)
                for addr, data in panel_data.items()
            ]
        except SerialWriteError:
            # propagate validation errors as-is
            raise

        try:
            async with self._tx_lock:
                for msg in messages:
                    bytes_written = await self._send_bytes_unlocked(msg)
                    if bytes_written != len(msg):
                        raise SerialWriteError(
                            f"Buffered write short: wrote {bytes_written}/{len(msg)} bytes"
                        )
                    if self.interpanel_delay > 0:
                        await asyncio.sleep(self.interpanel_delay)

                # Always flush at the end for buffered batch
                await self.flush_all_panels(locked=True)

            self.logger.debug(
                "Buffered batch write complete (%d panels)", len(messages)
            )

        except (SerialException, OSError, ValueError) as e:
            self.logger.debug("Buffered batch write failed", exc_info=True)
            raise SerialWriteError(f"Buffered batch write failed: {e}") from e

    async def flush_all_panels(self, *, locked: bool = False) -> None:
        """
        Public flush: refresh all buffered panels simultaneously.
        If `locked=True`, assumes the caller already holds `_tx_lock`.
        """
        flush_message = bytes([self.HEADER, FLUSH_COMMAND, 0xFF, self.EOT])
        try:
            if locked:
                n = await self._send_bytes_unlocked(flush_message)
            else:
                async with self._tx_lock:
                    n = await self._send_bytes_unlocked(flush_message)
            if n != len(flush_message):
                raise SerialFlushError(
                    f"Flush command failed - wrote {n}/{len(flush_message)} bytes"
                )
            self.logger.debug("Flush command sent successfully - all panels refreshed")

        except (SerialException, OSError, ValueError) as e:
            self.logger.debug("Failed to send flush command", exc_info=True)
            raise SerialFlushError(f"Failed to send flush command: {e}") from e


def create_writer(
    display_config: DisplayConfig, use_hardware: Optional[bool] = None
) -> SerialWriter:
    """
    Factory function to create the appropriate writer based on configuration.

    Args:
        display_config: Display configuration
        use_hardware: Override for hardware selection. If None, uses config.serial.mock

    Returns:
        SerialWriter: Either MockWriter or HardwareWriter
    """
    if use_hardware is None:
        use_hardware = not display_config.serial.mock

    if use_hardware:
        logger.info("Creating hardware serial writer")
        return HardwareWriter(display_config)
    else:
        logger.info("Creating mock serial writer")
        return MockWriter(display_config)
