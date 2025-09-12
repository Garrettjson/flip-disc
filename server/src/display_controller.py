"""
Display Controller - Policy/Orchestration Layer

This module contains the DisplayController class, which orchestrates flip-disc
display operations. It makes policy decisions about single vs multi-panel behavior,
buffering strategies, and flush timing.

Policy layer - uses pure classes (FrameMapper, ProtocolEncoder) and I/O boundary (SerialPort).
"""

import logging
from typing import Optional, List, Dict
import numpy as np

from .config import DisplayConfig, PanelConfig
from .frame_mapper import FrameMapper
from .protocol_encoder import ProtocolEncoder
from .serial_port import SerialPort, create_serial_port


logger = logging.getLogger(__name__)


class DisplayControllerError(Exception):
    """Base exception for display controller errors."""

    pass


class CanvasFrameError(DisplayControllerError):
    """Raised when canvas frame transmission fails."""

    pass


class TestPatternError(DisplayControllerError):
    """Raised when test pattern transmission fails."""

    pass


class NotConnectedError(DisplayControllerError):
    """Raised when attempting operations while not connected."""

    pass


class PanelFrameError(DisplayControllerError):
    """Raised when panel frame transmission fails."""

    pass


class DisplayController:
    """
    Policy/orchestration layer for flip-disc display communication.

    This controller makes high-level decisions about:
    - Single vs multi-panel refresh strategies
    - Buffered vs immediate display updates
    - When to flush buffered updates
    - Error handling and recovery

    Uses pure classes for logic and I/O boundary for hardware interaction.
    """

    def __init__(
        self,
        display_config: DisplayConfig,
        frame_mapper: Optional[FrameMapper] = None,
        protocol_encoder: Optional[ProtocolEncoder] = None,
        serial_port: Optional[SerialPort] = None,
        use_hardware: Optional[bool] = None,
    ):
        """
        Initialize display controller with dependencies.

        Args:
            display_config: Display configuration
            frame_mapper: Frame mapping logic (default: new instance)
            protocol_encoder: Protocol encoding logic (default: new instance)
            serial_port: Serial I/O boundary (default: auto-created)
            use_hardware: Force hardware vs mock (default: from config)
        """
        self.config = display_config

        # Pure logic components
        self.frame_mapper = frame_mapper or FrameMapper()
        self.protocol_encoder = protocol_encoder or ProtocolEncoder()

        # I/O boundary
        self.serial_port = serial_port or create_serial_port(
            display_config.serial, use_hardware
        )

        # Panel lookup for easy access
        self._panels_by_address = {panel.address: panel for panel in self.config.panels}

        self.logger = logging.getLogger(f"{__name__}")

        self.logger.info(
            f"Display controller initialized with {len(self.config.panels)} panels"
        )
        self.logger.info(
            f"Canvas dimensions: {self.config.canvas_size.w}x{self.config.canvas_size.h}"
        )

    async def connect(self) -> None:
        """
        Connect to the display hardware.

        Raises:
            DisplayControllerError: If connection fails
        """
        try:
            await self.serial_port.connect()
            self.logger.info("Display controller connected successfully")
        except Exception as e:
            raise DisplayControllerError(f"Failed to connect: {e}") from e

    async def disconnect(self) -> None:
        """
        Disconnect from display hardware.

        Raises:
            DisplayControllerError: If disconnection fails
        """
        try:
            await self.serial_port.disconnect()
            self.logger.info("Display controller disconnected")
        except Exception as e:
            raise DisplayControllerError(f"Failed to disconnect: {e}") from e

    def is_connected(self) -> bool:
        """Check if display controller is connected."""
        return self.serial_port.is_connected()

    async def send_canvas_frame(self, canvas_bits: bytes) -> None:
        """
        Send a full canvas frame to all panels.

        Policy decisions:
        - Maps canvas to individual panels using FrameMapper
        - Uses buffered updates for multi-panel displays
        - Uses immediate updates for single-panel displays
        - Automatically flushes buffered updates

        Args:
            canvas_bits: Packed bitmap for entire canvas

        Raises:
            NotConnectedError: If not connected to display hardware
            CanvasFrameError: If canvas frame transmission fails
        """
        if not self.is_connected():
            raise NotConnectedError("Cannot send canvas frame - not connected")

        try:
            # Pure logic: map canvas to panel data
            panel_arrays = self.frame_mapper.map_canvas_to_panels(
                canvas_bits,
                self.config.canvas_size.w,
                self.config.canvas_size.h,
                self.config.panels,
            )

            if not panel_arrays:
                raise CanvasFrameError("No panel data generated from canvas")

            # Send to all panels with appropriate policy
            await self._send_panel_arrays(panel_arrays)
            self.logger.debug(f"Canvas frame sent to {len(panel_arrays)} panels")

        except NotConnectedError:
            raise
        except CanvasFrameError:
            raise
        except Exception as e:
            raise CanvasFrameError(f"Error sending canvas frame: {e}") from e

    async def send_panel_frame(
        self, panel_address: int, frame_data: np.ndarray
    ) -> None:
        """
        Send a frame directly to a specific panel.

        Args:
            panel_address: RS-485 address of the panel
            frame_data: numpy array of pixel data (height x width)

        Raises:
            NotConnectedError: If not connected to display hardware
            PanelFrameError: If panel frame transmission fails
        """
        if not self.is_connected():
            raise NotConnectedError("Cannot send panel frame - not connected")

        panel = self._panels_by_address.get(panel_address)
        if not panel:
            raise PanelFrameError(f"Unknown panel address {panel_address}")

        # Validate frame dimensions
        expected_shape = (panel.size.h, panel.size.w)
        if frame_data.shape != expected_shape:
            raise PanelFrameError(
                f"Panel {panel.id} frame shape {frame_data.shape} != expected {expected_shape}"
            )

        try:
            # Send as single panel (immediate policy for single panels)
            await self._send_panel_arrays({panel_address: frame_data})
            self.logger.debug(
                f"Frame sent to panel '{panel.id}' (address {panel_address})"
            )
        except Exception as e:
            raise PanelFrameError(
                f"Failed to send frame to panel '{panel.id}' (address {panel_address}): {e}"
            ) from e

    async def send_test_pattern(self, pattern: str = "checkerboard") -> None:
        """
        Send a test pattern to all panels.

        Args:
            pattern: Pattern type ("checkerboard", "border", "solid", "clear")

        Raises:
            TestPatternError: If test pattern transmission fails
        """
        try:
            # Pure logic: create test pattern
            canvas_bits = self.frame_mapper.create_test_pattern(
                self.config.canvas_size.w, self.config.canvas_size.h, pattern
            )

            await self.send_canvas_frame(canvas_bits)
            self.logger.info(f"Test pattern '{pattern}' sent successfully")

        except (NotConnectedError, CanvasFrameError) as e:
            raise TestPatternError(
                f"Failed to send test pattern '{pattern}': {e}"
            ) from e
        except Exception as e:
            raise TestPatternError(
                f"Error creating test pattern '{pattern}': {e}"
            ) from e

    async def _send_panel_arrays(self, panel_arrays: Dict[int, np.ndarray]) -> None:
        """
        Send panel arrays using appropriate policy decisions.

        Policy decisions:
        - Multi-panel: use buffered refresh with flush
        - Single-panel: use immediate refresh (no flush needed)

        Args:
            panel_arrays: Dict mapping panel address to numpy array data
        """
        # Convert numpy arrays to protocol payloads (column-wise strips, LSB=top)
        panel_payloads = {}
        for address, array in panel_arrays.items():
            packed_cols = np.packbits(array.astype(np.uint8), axis=0, bitorder="little")
            panel_payloads[address] = packed_cols[0].tobytes()

        # Generate protocol frames
        frames = list(
            self.protocol_encoder.encode_many(
                panel_payloads, self.config.protocol_config
            )
        )

        # Policy decision: flush for multi-panel displays
        if self._should_flush_after_panels(len(panel_arrays)):
            flush_frame = self.protocol_encoder.encode_flush()
            frames.append(flush_frame)

        # Send via I/O boundary
        await self.serial_port.write_frames(frames)

    def _should_flush_after_panels(self, panel_count: int) -> bool:
        """
        Policy decision: determine if we should flush after panel updates.

        Policy:
        - Multi-panel displays: use buffered refresh with flush for synchronization
        - Single-panel displays: use immediate refresh (no flush needed)

        Args:
            panel_count: Number of panels being updated

        Returns:
            bool: True if should flush, False otherwise
        """
        return panel_count > 1 and self.config.protocol_config.supports_buffered

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
