from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Iterable, Optional

import numpy as np
from serial import SerialException
from aioserial import AioSerial

from .config import DisplayConfig
from .protocol_config import FLUSH_COMMAND

logger = logging.getLogger(__name__)


class SerialConnectError(Exception):
    """Raised for transport-level serial errors."""

    pass


class ProtocolEncoder:
    """Pure framing encoder for panel payloads.

    Frame format (per your protocol docs):
      [0x80, address, len_hi, len_lo, <payload bytes...>, 0x8F]
    """

    HEADER = 0x80
    EOT = 0x8F

    def encode_panel_frame(self, address: int, payload: bytes) -> bytes:
        n = len(payload)
        return (
            bytes([self.HEADER, address & 0xFF, (n >> 8) & 0xFF, n & 0xFF])
            + payload
            + bytes([self.EOT])
        )

    def encode_many(self, panel_payloads: Dict[int, bytes]) -> Iterable[bytes]:
        for addr, payload in panel_payloads.items():
            yield self.encode_panel_frame(addr, payload)

    def encode_flush(self, flush_command: bytes) -> bytes:
        # In case your FLUSH command already includes header/EOT, just pass-through.
        # If not, you could wrap it similarly to encode_panel_frame.
        return flush_command


class SerialWriter(ABC):
    def __init__(self, display_config: DisplayConfig):
        self.display_config = display_config
        self.protocol_config = display_config.protocol_config
        self.encoder = ProtocolEncoder()

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    async def write_panel_data(self, panel_arrays: Dict[int, np.ndarray]) -> None:
        """Encode frames and write them out (no refresh/flush policy here)."""
        ...

    async def flush(self) -> None:
        """Send a flush/refresh command if the protocol uses deferred refresh."""
        if self.protocol_config.supports_buffered:
            flush_frame = self.encoder.encode_flush(bytes([FLUSH_COMMAND]))
            await self._write_raw([flush_frame])

    # Internal hook for subclasses to implement actual transport write
    @abstractmethod
    async def _write_raw(self, frames: Iterable[bytes]) -> None: ...


class HardwareWriter(SerialWriter):
    def __init__(self, display_config: DisplayConfig):
        super().__init__(display_config)
        sc = display_config.serial
        self._port = sc.port
        self._baudrate = sc.baudrate
        self._timeout = sc.timeout
        self._serial: Optional[AioSerial] = None
        self._io_lock = asyncio.Lock()

    async def connect(self) -> None:
        async with self._io_lock:
            try:
                self._serial = AioSerial(
                    port=self._port, baudrate=self._baudrate, timeout=self._timeout
                )
                await asyncio.sleep(0)
            except (SerialException, OSError, ValueError) as e:
                self._serial = None
                raise SerialConnectError(f"Serial connect failed: {e}") from e

    async def disconnect(self) -> None:
        async with self._io_lock:
            if self._serial:
                try:
                    self._serial.close()
                except Exception as e:
                    raise SerialConnectError(f"Serial disconnect failed: {e}") from e
                finally:
                    self._serial = None

    def is_connected(self) -> bool:
        return self._serial is not None

    async def write_panel_data(self, panel_arrays: Dict[int, np.ndarray]) -> None:
        panel_payloads = {}
        for addr, array in panel_arrays.items():
            panel_payloads[addr] = np.packbits(array, axis=1, bitorder="big").tobytes()

        frames = list(self.encoder.encode_many(panel_payloads))
        await self._write_raw(frames)

        # Auto-flush for buffered refresh mode
        if self.protocol_config.supports_buffered and len(panel_arrays) > 1:
            await self.flush()

    async def _write_raw(self, frames: Iterable[bytes]) -> None:
        if not self._serial:
            raise SerialConnectError("Not connected")

        for frame in frames:
            n = await self._serial.write_async(frame)
            if n != len(frame):
                raise SerialConnectError(f"Short write: {n}/{len(frame)}")


class MockWriter(SerialWriter):
    def __init__(self, display_config: DisplayConfig):
        super().__init__(display_config)
        self._connected = False
        self._last_payload_sizes: Dict[int, int] = {}

    async def connect(self) -> None:
        self._connected = True
        logger.info("[MOCK] Connected")

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("[MOCK] Disconnected")

    def is_connected(self) -> bool:
        return self._connected

    async def write_panel_data(self, panel_arrays: Dict[int, np.ndarray]) -> None:
        # Pack numpy arrays to bytes for size calculation
        panel_payloads = {}
        for addr, array in panel_arrays.items():
            panel_payloads[addr] = np.packbits(array, axis=1, bitorder="big").tobytes()

        self._last_payload_sizes = {addr: len(b) for addr, b in panel_payloads.items()}
        total = sum(self._last_payload_sizes.values())
        logger.info(
            "[MOCK] write_panel_data: %d panels, %d bytes total",
            len(panel_arrays),
            total,
        )
        # Simulate a tiny async delay
        await asyncio.sleep(0)

        # Auto-flush for buffered refresh mode
        if self.protocol_config.supports_buffered and len(panel_arrays) > 1:
            await self.flush()

    async def _write_raw(self, frames: Iterable[bytes]) -> None:
        count = sum(1 for _ in frames)
        logger.info("[MOCK] _write_raw: %d frames", count)
        await asyncio.sleep(0)


def create_writer(
    display_config: DisplayConfig, use_hardware: Optional[bool] = None
) -> SerialWriter:
    """
    Choose between MockWriter and HardwareWriter.

    If `use_hardware` is None, we invert `config.serial.mock` to decide.
    """
    if use_hardware is None:
        use_hardware = not display_config.serial.mock

    if use_hardware:
        logger.info("Creating hardware serial writer")
        return HardwareWriter(display_config)
    else:
        logger.info("Creating mock serial writer")
        return MockWriter(display_config)
