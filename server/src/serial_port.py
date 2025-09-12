"""
Serial Port I/O Boundary

This module provides the SerialPort class, which handles all serial I/O operations
for flip-disc displays. It abstracts away the hardware/mock distinction and provides
a clean interface for serial communication.

I/O boundary class - handles all hardware interaction and connection management.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Iterable, Optional
from serial import SerialException
from aioserial import AioSerial

from .config import SerialConfig


logger = logging.getLogger(__name__)


class SerialConnectionError(Exception):
    """Raised when serial connection operations fail."""

    pass


class SerialPort(ABC):
    """
    Abstract base class for serial port communication.

    Defines the I/O boundary interface for serial communication with
    flip-disc displays. Implementations handle hardware vs mock communication.
    """

    @abstractmethod
    async def connect(self) -> None:
        """
        Connect to the serial port.

        Raises:
            SerialConnectionError: If connection fails
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Disconnect from the serial port.

        Raises:
            SerialConnectionError: If disconnection fails
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if serial port is connected."""
        pass

    @abstractmethod
    async def write_frames(self, frames: Iterable[bytes]) -> None:
        """
        Write protocol frames to the serial port.

        Args:
            frames: Encoded protocol frames to transmit

        Raises:
            SerialConnectionError: If write operation fails
        """
        pass


class HardwareSerialPort(SerialPort):
    """
    Hardware serial port implementation using aioserial.

    Manages actual serial communication with flip-disc hardware via RS-485.
    """

    def __init__(self, config: SerialConfig):
        self.config = config
        self._serial: Optional[AioSerial] = None
        self._io_lock = asyncio.Lock()

    async def connect(self) -> None:
        """Connect to hardware serial port."""
        async with self._io_lock:
            try:
                self._serial = AioSerial(
                    port=self.config.port,
                    baudrate=self.config.baudrate,
                    timeout=self.config.timeout,
                )
                # Give the connection a moment to stabilize
                await asyncio.sleep(0.1)
                logger.info(f"Connected to hardware serial port {self.config.port}")

            except (SerialException, OSError, ValueError) as e:
                self._serial = None
                raise SerialConnectionError(
                    f"Hardware serial connect failed: {e}"
                ) from e

    async def disconnect(self) -> None:
        """Disconnect from hardware serial port."""
        async with self._io_lock:
            if self._serial:
                try:
                    self._serial.close()
                    logger.info("Disconnected from hardware serial port")
                except Exception as e:
                    raise SerialConnectionError(
                        f"Hardware serial disconnect failed: {e}"
                    ) from e
                finally:
                    self._serial = None

    def is_connected(self) -> bool:
        """Check if hardware serial port is connected."""
        return self._serial is not None

    async def write_frames(self, frames: Iterable[bytes]) -> None:
        """Write frames to hardware serial port."""
        if not self._serial:
            raise SerialConnectionError("Not connected to hardware")

        try:
            for frame in frames:
                bytes_written = await self._serial.write_async(frame)
                if bytes_written != len(frame):
                    raise SerialConnectionError(
                        f"Short write: {bytes_written}/{len(frame)} bytes"
                    )
        except Exception as e:
            raise SerialConnectionError(f"Hardware write failed: {e}") from e


class MockSerialPort(SerialPort):
    """
    Mock serial port implementation for testing and development.

    Simulates serial communication without actual hardware interaction.
    Logs operations for debugging purposes.
    """

    def __init__(self, config: SerialConfig):
        self.config = config
        self._connected = False

    async def connect(self) -> None:
        """Simulate connecting to serial port."""
        await asyncio.sleep(0.01)  # Simulate connection delay
        self._connected = True
        logger.info(f"[MOCK] Connected to serial port {self.config.port}")

    async def disconnect(self) -> None:
        """Simulate disconnecting from serial port."""
        await asyncio.sleep(0.01)  # Simulate disconnection delay
        self._connected = False
        logger.info("[MOCK] Disconnected from serial port")

    def is_connected(self) -> bool:
        """Check if mock serial port is connected."""
        return self._connected

    async def write_frames(self, frames: Iterable[bytes]) -> None:
        """Simulate writing frames to serial port."""
        if not self._connected:
            raise SerialConnectionError("Not connected to mock serial")

        frame_count = 0
        total_bytes = 0

        for frame in frames:
            frame_count += 1
            total_bytes += len(frame)

        logger.info(f"[MOCK] Wrote {frame_count} frames ({total_bytes} bytes)")

        # Simulate transmission delay
        await asyncio.sleep(0.001 * frame_count)


def create_serial_port(
    config: SerialConfig, use_hardware: Optional[bool] = None
) -> SerialPort:
    """
    Factory function to create appropriate serial port implementation.

    Args:
        config: Serial configuration
        use_hardware: Force hardware (True) or mock (False). If None, uses config.mock

    Returns:
        SerialPort: Hardware or mock implementation
    """
    if use_hardware is None:
        use_hardware = not config.mock

    if use_hardware:
        logger.info("Creating hardware serial port")
        return HardwareSerialPort(config)
    else:
        logger.info("Creating mock serial port")
        return MockSerialPort(config)
