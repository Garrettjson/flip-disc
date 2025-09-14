"""Serial port abstraction for flip-disc display communication."""

import asyncio
import logging
from abc import ABC, abstractmethod

try:
    from aioserial import AioSerial
    from serial import SerialException

    HAS_AIOSERIAL = True
except ImportError:
    HAS_AIOSERIAL = False

    # Fallback stubs for development without hardware
    class AioSerial:
        pass

    class SerialException(Exception):  # noqa: N818 - matches upstream name
        pass


from .config import SerialConfig
from .exceptions import HardwareError, SerialConnectionError
from .hw.formats import encode_flush

logger = logging.getLogger(__name__)


class SerialPort(ABC):
    """Abstract base class for serial port communication."""

    @abstractmethod
    async def connect(self) -> None:
        """Connect to the serial port."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the serial port."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if serial port is connected."""

    @abstractmethod
    async def write_frame(self, frame_data: bytes) -> None:
        """Write frame data to the serial port."""

    @abstractmethod
    async def write_flush(self) -> None:
        """Issue a display flush after segmented writes."""


class HardwareSerialPort(SerialPort):
    """Hardware serial port implementation using aioserial."""

    def __init__(self, config: SerialConfig):
        if not HAS_AIOSERIAL:
            raise HardwareError(
                "aioserial not available - install with: pip install aioserial"
            )

        self.config = config
        self._serial: AioSerial | None = None
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

    async def write_frame(self, frame_data: bytes) -> None:
        """Write frame data to hardware serial port with I/O locking.

        Using an async lock prevents interleaved writes from multiple coroutines
        and ensures each frame is transmitted atomically.
        """
        if not self._serial:
            raise SerialConnectionError("Not connected to hardware")

        async with self._io_lock:
            try:
                bytes_written = await self._serial.write_async(frame_data)
                if bytes_written != len(frame_data):
                    raise SerialConnectionError(
                        f"Short write: {bytes_written}/{len(frame_data)} bytes"
                    )
            except Exception as e:
                raise SerialConnectionError(f"Hardware write failed: {e}") from e

    async def write_flush(self) -> None:
        """Issue a protocol flush to the hardware."""
        async with self._io_lock:
            if not self._serial:
                raise SerialConnectionError("Not connected to hardware")
            try:
                data = encode_flush()
                bytes_written = await self._serial.write_async(data)
                if bytes_written != len(data):
                    raise SerialConnectionError(
                        f"Short flush write: {bytes_written}/{len(data)} bytes"
                    )
            except Exception as e:
                raise SerialConnectionError(f"Hardware flush failed: {e}") from e


class MockSerialPort(SerialPort):
    """Mock serial port implementation for testing and development."""

    def __init__(self, config: SerialConfig):
        self.config = config
        self._connected = False
        self._bytes_written = 0
        self._frames_written = 0
        self._io_lock = asyncio.Lock()

    async def connect(self) -> None:
        """Simulate connecting to serial port."""
        await asyncio.sleep(0.01)  # Simulate connection delay
        self._connected = True
        logger.info(f"[MOCK] Connected to serial port {self.config.port}")

    async def disconnect(self) -> None:
        """Simulate disconnecting from serial port."""
        await asyncio.sleep(0.01)  # Simulate disconnection delay
        self._connected = False
        logger.info(
            f"[MOCK] Disconnected from serial port (wrote {self._frames_written} frames, {self._bytes_written} bytes)"
        )

    def is_connected(self) -> bool:
        """Check if mock serial port is connected."""
        return self._connected

    async def write_frame(self, frame_data: bytes) -> None:
        """Simulate writing frame data to serial port with I/O locking."""
        if not self._connected:
            raise SerialConnectionError("Not connected to mock serial")

        async with self._io_lock:
            self._frames_written += 1
            self._bytes_written += len(frame_data)

            logger.debug(
                f"[MOCK] Wrote frame {self._frames_written} ({len(frame_data)} bytes)"
            )

            # Simulate transmission delay based on baud rate
            bit_time = len(frame_data) * 8 / self.config.baudrate
            await asyncio.sleep(min(bit_time, 0.01))  # Cap at 10ms for testing

    async def write_flush(self) -> None:
        """Simulate a display flush after segmented writes."""
        async with self._io_lock:
            logger.debug("[MOCK] Flush issued")


def create_serial_port(config: SerialConfig, force_mock: bool = False) -> SerialPort:
    """Factory function to create appropriate serial port implementation."""
    if force_mock or config.mock:
        logger.info("Creating mock serial port")
        return MockSerialPort(config)
    logger.info("Creating hardware serial port")
    return HardwareSerialPort(config)
