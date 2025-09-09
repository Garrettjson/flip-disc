from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List
import numpy as np

from aioserial import AioSerial

from .config import DisplayConfig, PanelConfig

logger = logging.getLogger(__name__)


class SerialWriter(ABC):
    """
    Abstract base class for serial writers.
    Defines the interface for writing data to flip disc panels.
    """

    @abstractmethod
    async def write_panel_data(self, panel_data: Dict[int, np.ndarray]) -> bool:
        """
        Write data to multiple panels.

        Args:
            panel_data: Dict mapping panel addresses to numpy arrays of pixel data

        Returns:
            bool: True if all writes successful, False otherwise
        """
        pass

    @abstractmethod
    async def write_single_panel(self, address: int, data: np.ndarray) -> bool:
        """
        Write data to a single panel.

        Args:
            address: Panel RS-485 address
            data: Numpy array of pixel data (height x width)

        Returns:
            bool: True if write successful, False otherwise
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

    async def write_single_panel(self, address: int, data: np.ndarray) -> bool:
        """Mock single panel write with detailed logging."""
        if not self.connected:
            self.logger.error("MOCK: Not connected - cannot write")
            return False

        panel = self._panels_by_address.get(address)
        if not panel:
            self.logger.error(f"MOCK: Unknown panel address {address}")
            return False

        # Validate data shape
        expected_shape = (panel.size.h, panel.size.w)
        if data.shape != expected_shape:
            self.logger.error(
                f"MOCK: Panel {panel.id} data shape {data.shape} != expected {expected_shape}"
            )
            return False

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
        return True

    async def write_panel_data(self, panel_data: Dict[int, np.ndarray]) -> bool:
        """Mock multi-panel write with buffered strategy simulation."""
        if not self.connected:
            self.logger.error("MOCK: Not connected - cannot write panel data")
            return False

        panel_count = len(panel_data)
        use_buffered = panel_count > 1
        
        if use_buffered:
            self.logger.info(f"MOCK: Buffered write to {panel_count} panels (prevents visual artifacts)")
        else:
            self.logger.info(f"MOCK: Direct write to {panel_count} panel")

        success = True
        for address, data in panel_data.items():
            panel_success = await self.write_single_panel(address, data)
            if not panel_success:
                success = False

        # Simulate flush command for multi-panel updates
        if use_buffered and success:
            await asyncio.sleep(0.001)  # Simulate flush command timing
            self.logger.info("MOCK: Flush command sent - all panels refresh simultaneously")

        if success:
            self.logger.info("MOCK: All panel writes completed successfully")
        else:
            self.logger.error("MOCK: Some panel writes failed")

        return success


class HardwareWriter(SerialWriter):
    """
    Real serial writer for actual hardware communication.
    Uses aioserial for async RS-485 communication with flip disc panels.
    """

    # Protocol constants
    HEADER = 0x80
    EOT = 0x8F

    # Configuration byte mapping
    _CFG_MAP_INSTANT = {
        0: 0x82,  # config only
        7: 0x87,  # 7-byte data
        14: 0x92,  # 14-byte data
        28: 0x83,  # 28-byte data
    }

    _CFG_MAP_NON_INSTANT = {
        14: 0x93,  # 14-byte data (non-instant)
        28: 0x84,  # 28-byte data (non-instant)
    }

    def __init__(
        self,
        display_config: DisplayConfig,
        instant_refresh: bool = True,
        interpanel_delay_us: int = 0,
    ):
        self.config = display_config
        self.instant_refresh = instant_refresh
        self.interpanel_delay = interpanel_delay_us / 1_000_000.0  # Convert to seconds
        self.serial: AioSerial | None = None

        # Create panel lookup
        self._panels_by_address = {
            panel.address: panel for panel in self.config.enabled_panels
        }

        self.logger = logging.getLogger(f"{__name__}.hardware")

    async def connect(self) -> bool:
        """Connect to real serial hardware."""
        try:
            # Configure serial based on config
            self.serial = AioSerial(
                self.config.serial.port,
                self.config.serial.baudrate,
                timeout=self.config.serial.timeout,
            )

            self.logger.info(
                f"Connected to {self.config.serial.port} at {self.config.serial.baudrate} baud"
            )
            self.logger.info(
                f"Instant refresh: {self.instant_refresh}, interpanel delay: {self.interpanel_delay*1000:.1f}ms"
            )

            return True

        except Exception as e:
            self.logger.error(
                f"Failed to connect to serial port {self.config.serial.port}: {e}"
            )
            return False

    async def disconnect(self) -> None:
        """Disconnect from serial hardware."""
        if self.serial:
            try:
                self.serial.close()
                self.logger.info("Serial connection closed")
            except Exception as e:
                self.logger.warning(f"Error closing serial connection: {e}")
            finally:
                self.serial = None

    def is_connected(self) -> bool:
        """Check if serial connection is active."""
        return self.serial is not None and not self.serial.is_closing

    def _pack_panel_data(self, data: np.ndarray) -> bytes:
        """Pack numpy array into bytes for transmission."""
        # Pack 8 pixels per byte, MSB first
        flat_data = data.flatten()
        packed_bytes = []

        for i in range(0, len(flat_data), 8):
            byte_value = 0
            for bit_pos in range(8):
                if i + bit_pos < len(flat_data):
                    if flat_data[i + bit_pos]:
                        byte_value |= 1 << (7 - bit_pos)
            packed_bytes.append(byte_value)

        return bytes(packed_bytes)

    def _build_message(self, panel: PanelConfig, data: bytes) -> bytes:
        """Build complete serial message for panel."""
        data_len = len(data)

        # Select config byte based on data length and refresh mode
        if self.instant_refresh:
            cfg_byte = self._CFG_MAP_INSTANT.get(data_len, 0x83)
        else:
            cfg_byte = self._CFG_MAP_NON_INSTANT.get(data_len, 0x84)

        # Build message: HEADER + CFG + ADDRESS + DATA + EOT
        message = (
            bytes([self.HEADER, cfg_byte, panel.address & 0xFF])
            + data
            + bytes([self.EOT])
        )

        return message

    async def write_single_panel(self, address: int, data: np.ndarray) -> bool:
        """Write data to a single panel via serial."""
        if not self.is_connected():
            self.logger.error("Not connected to serial port")
            return False

        panel = self._panels_by_address.get(address)
        if not panel:
            self.logger.error(f"Unknown panel address {address}")
            return False

        try:
            # Validate data shape
            expected_shape = (panel.size.h, panel.size.w)
            if data.shape != expected_shape:
                self.logger.error(
                    f"Panel {panel.id} data shape {data.shape} != expected {expected_shape}"
                )
                return False

            # Pack and build message
            packed_data = self._pack_panel_data(data)
            message = self._build_message(panel, packed_data)

            # Send message
            bytes_written = await self.serial.write_async(message)

            if bytes_written == len(message):
                pixels_on = np.sum(data)
                self.logger.debug(
                    f"Panel '{panel.id}' (addr {address}) - {pixels_on}/{data.size} pixels, {len(message)} bytes"
                )
                return True
            else:
                self.logger.error(
                    f"Panel {panel.id} - wrote {bytes_written}/{len(message)} bytes"
                )
                return False

        except Exception as e:
            self.logger.error(f"Failed to write to panel {panel.id}: {e}")
            return False

    async def write_panel_data(self, panel_data: Dict[int, np.ndarray]) -> bool:
        """
        Write data to multiple panels using buffered strategy.
        
        For multi-panel displays, uses buffered writes followed by a single flush
        to ensure all panels update simultaneously, preventing the "wipe across" effect.
        """
        if not self.is_connected():
            self.logger.error("Not connected to serial port")
            return False

        panel_count = len(panel_data)
        self.logger.debug(f"Writing to {panel_count} panels with buffered strategy")

        # Use buffered writes for multi-panel updates to prevent visual artifacts
        use_buffered = panel_count > 1
        
        if use_buffered:
            # Temporarily disable instant refresh for buffering
            original_instant_refresh = self.instant_refresh
            self.instant_refresh = False
            
        success = True
        try:
            # Send data to all panels (buffered, no immediate display update)
            for address, data in panel_data.items():
                panel_success = await self.write_single_panel(address, data)
                if not panel_success:
                    success = False
                    break

                # Inter-panel delay if configured
                if self.interpanel_delay > 0:
                    await asyncio.sleep(self.interpanel_delay)

            # If buffered mode and all writes successful, send flush command
            if use_buffered and success:
                flush_success = await self._flush_all_panels()
                if not flush_success:
                    success = False
                    
        finally:
            # Restore original instant refresh setting
            if use_buffered:
                self.instant_refresh = original_instant_refresh

        if success:
            self.logger.debug(f"All {panel_count} panel writes completed successfully")
        else:
            self.logger.error("Some panel writes failed")

        return success

    async def _flush_all_panels(self) -> bool:
        """
        Send flush command to refresh all buffered panels simultaneously.
        
        Sends the 0x82 config command (refresh/instant) to cause all panels
        to apply their buffered data at the same time.
        """
        try:
            # Build flush message: HEADER + 0x82 (refresh config) + dummy address + EOT
            # Address doesn't matter for broadcast refresh, using 0xFF
            flush_message = bytes([self.HEADER, 0x82, 0xFF, self.EOT])
            
            bytes_written = await self.serial.write_async(flush_message)
            
            if bytes_written == len(flush_message):
                self.logger.debug("Flush command sent successfully - all panels refreshed")
                return True
            else:
                self.logger.error(f"Flush command failed - wrote {bytes_written}/{len(flush_message)} bytes")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to send flush command: {e}")
            return False


def create_writer(
    display_config: DisplayConfig, use_hardware: bool = None
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
