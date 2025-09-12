import logging
import numpy as np

from typing import Optional, List

from .config import DisplayConfig, PanelConfig
from .serial_writer import SerialWriter, create_writer
from .panel_mapper import update_panels

logger = logging.getLogger(__name__)


class CanvasFrameError(Exception):
    """Raised when canvas frame transmission fails."""

    pass


class TestPatternError(Exception):
    """Raised when test pattern transmission fails."""

    pass


class SerialController:
    """
    High-level controller for flip disc display communication.

    This controller handles:
    - Canvas-to-panel mapping using panel_mapper
    - Serial communication via pluggable SerialWriter implementations
    - Panel management and validation
    """

    def __init__(
        self, display_config: DisplayConfig, use_hardware: Optional[bool] = None
    ):
        self.config = display_config
        self.writer: SerialWriter = create_writer(display_config, use_hardware)

        # Create panel lookup for easy access
        self._panels_by_address = {panel.address: panel for panel in self.config.panels}

        self.logger = logging.getLogger(f"{__name__}")

        self.logger.info(
            f"Serial controller initialized with {len(self.config.panels)} panels"
        )
        self.logger.info(
            f"Canvas dimensions: {self.config.canvas_size.w}x{self.config.canvas_size.h}"
        )

    async def connect(self) -> None:
        """
        Connect to the serial interface.

        Raises:
            SerialTransportError: If connection fails
        """
        await self.writer.connect()
        self.logger.info("Serial controller connected successfully")

    async def disconnect(self) -> None:
        """Disconnect from serial interface."""
        await self.writer.disconnect()
        self.logger.info("Serial controller disconnected")

    def is_connected(self) -> bool:
        """Check if serial connection is active."""
        return self.writer.is_connected()

    async def send_canvas_frame(self, canvas_bits: bytes) -> bool:
        """
        Send a full canvas frame to all panels.

        This method:
        1. Takes the full canvas bitmap
        2. Maps it to individual panel data using panel_mapper
        3. Sends the panel data via the serial writer

        Args:
            canvas_bits: Packed bitmap for entire canvas

        Returns:
            bool: True if all panels updated successfully, False otherwise
        """
        if not self.is_connected():
            self.logger.error("Cannot send canvas frame - not connected")
            return False

        try:
            # Map canvas to panel data (now returns numpy arrays directly)
            panel_arrays = update_panels(
                canvas_bits,
                self.config.canvas_size.w,
                self.config.canvas_size.h,
                self.config,
            )

            if not panel_arrays:
                self.logger.warning("No panel data generated from canvas")
                return False

            # Send to all panels
            await self.writer.write_panel_data(panel_arrays)
            self.logger.debug(f"Canvas frame sent to {len(panel_arrays)} panels")
            return True

        except Exception as e:
            self.logger.error(f"Error sending canvas frame: {e}")
            return False

    async def send_panel_frame(
        self, panel_address: int, frame_data: np.ndarray
    ) -> bool:
        """
        Send a frame directly to a specific panel.

        Args:
            panel_address: RS-485 address of the panel
            frame_data: numpy array of pixel data (height x width)

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_connected():
            self.logger.error("Cannot send panel frame - not connected")
            return False

        panel = self._panels_by_address.get(panel_address)
        if not panel:
            self.logger.error(f"Unknown panel address {panel_address}")
            return False

        # Validate frame dimensions
        expected_shape = (panel.size.h, panel.size.w)
        if frame_data.shape != expected_shape:
            self.logger.error(
                f"Panel {panel.id} frame shape {frame_data.shape} != expected {expected_shape}"
            )
            return False

        try:
            # Send as single panel numpy array (will be packed at transmission boundary)
            await self.writer.write_panel_data({panel_address: frame_data})
            self.logger.debug(
                f"Frame sent to panel '{panel.id}' (address {panel_address})"
            )
            return True
        except Exception as e:
            self.logger.error(
                f"Failed to send frame to panel '{panel.id}' (address {panel_address}): {e}"
            )
            return False

    async def send_test_pattern(self, pattern: str = "checkerboard") -> bool:
        """
        Send a test pattern to all panels.

        Args:
            pattern: Pattern type ("checkerboard", "border", "solid", "clear")

        Returns:
            bool: True if successful, False otherwise
        """
        from .panel_mapper import create_test_pattern

        try:
            canvas_bits = create_test_pattern(self.config, pattern)
            success = await self.send_canvas_frame(canvas_bits)

            if success:
                self.logger.info(f"Test pattern '{pattern}' sent successfully")
            else:
                self.logger.error(f"Failed to send test pattern '{pattern}'")

            return success

        except Exception as e:
            self.logger.error(f"Error sending test pattern: {e}")
            return False

    def get_panel_by_address(self, address: int) -> Optional[PanelConfig]:
        """Get panel configuration by address."""
        return self._panels_by_address.get(address)

    def get_canvas_dimensions(self) -> tuple[int, int]:
        """Get canvas dimensions as (height, width)."""
        return (self.config.canvas_size.h, self.config.canvas_size.w)

    def get_enabled_panel_addresses(self) -> List[int]:
        """Get list of panel addresses."""
        return [panel.address for panel in self.config.panels]

    def get_display_stats(self) -> dict:
        """Get display statistics and information."""
        return {
            "canvas_size": f"{self.config.canvas_size.w}x{self.config.canvas_size.h}",
            "panel_count": len(self.config.panels),
            "panels": [
                {
                    "id": panel.id,
                    "address": panel.address,
                    "size": f"{panel.size.w}x{panel.size.h}",
                    "position": f"({panel.origin.x},{panel.origin.y})",
                    "orientation": panel.orientation,
                }
                for panel in self.config.panels
            ],
            "connected": self.is_connected(),
            "serial_config": {
                "port": self.config.serial.port,
                "baudrate": self.config.serial.baudrate,
                "mock": self.config.serial.mock,
            },
        }
