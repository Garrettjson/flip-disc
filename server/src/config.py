from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Literal

from .protocol_config import DataBytes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Point:
    """Represents a 2D coordinate point."""

    x: int
    y: int


@dataclass(frozen=True)
class Size:
    """Represents width and height dimensions."""

    w: int
    h: int


# Valid panel orientations
PanelOrientation = Literal["normal", "rot90", "rot180", "rot270", "fliph", "flipv"]


@dataclass
class PanelConfig:
    """
    Configuration for a single flip disc panel.

    Attributes:
        id: Unique identifier for the panel
        origin: Top-left corner position on the canvas (x, y)
        size: Panel dimensions (width, height)
        orientation: Panel rotation/flip ("normal", "rot90", "rot180", "rot270", "fliph", "flipv")
        address: RS-485 address for serial communication (0-based)
        enabled: Whether this panel is active
    """

    id: str
    origin: Point
    size: Size
    orientation: PanelOrientation = "normal"
    address: int = 0
    enabled: bool = True

    def __post_init__(self):
        """Validate panel configuration."""
        if self.size.w <= 0 or self.size.h <= 0:
            raise ValueError(f"Panel {self.id}: Invalid size {self.size}")

        if self.origin.x < 0 or self.origin.y < 0:
            raise ValueError(f"Panel {self.id}: Invalid origin {self.origin}")

        if self.address < 0:
            raise ValueError(f"Panel {self.id}: Invalid address {self.address}")

    @property
    def bounds(self) -> tuple[Point, Point]:
        """Get panel bounds as (top_left, bottom_right) points."""
        return (
            self.origin,
            Point(self.origin.x + self.size.w, self.origin.y + self.size.h),
        )

    def overlaps_with(self, other: PanelConfig) -> bool:
        """Check if this panel overlaps with another panel."""
        self_tl, self_br = self.bounds
        other_tl, other_br = other.bounds

        return not (
            self_br.x <= other_tl.x  # self is to the left of other
            or other_br.x <= self_tl.x  # other is to the left of self
            or self_br.y <= other_tl.y  # self is above other
            or other_br.y <= self_tl.y  # other is above self
        )


@dataclass
class SerialConfig:
    """Serial communication configuration."""

    port: str = "/dev/ttyUSB0"
    baudrate: int = 9600
    timeout: float = 1.0
    mock: bool = False  # Use mock serial controller for testing


@dataclass
class DisplayConfig:
    """
    Complete display configuration with simplified grid-based panel layout.

    Attributes:
        panel_type: Type of panels used (all panels must be same type)
        columns: Number of panel columns (horizontal)
        rows: Number of panel rows (vertical)
        serial: Serial communication settings
        refresh_rate: Target refresh rate in FPS
        buffer_duration: Frame buffer duration in seconds

    Computed attributes:
        canvas_size: Overall canvas dimensions (auto-calculated)
        panels: List of panel configurations (auto-generated)
    """

    panel_type: DataBytes
    columns: int
    rows: int
    serial: SerialConfig
    refresh_rate: float = 30.0
    buffer_duration: float = 0.5

    # Auto-computed attributes (set in __post_init__)
    canvas_size: Optional[Size] = None
    panels: List[PanelConfig] = field(default_factory=list)

    def __post_init__(self):
        """Validate configuration and auto-generate canvas size and panel layout."""
        # Validate basic parameters
        if self.columns <= 0:
            raise ValueError(f"Invalid columns: {self.columns}")
        if self.rows <= 0:
            raise ValueError(f"Invalid rows: {self.rows}")
        if self.refresh_rate <= 0 or self.refresh_rate > 30:
            raise ValueError(f"Invalid refresh rate: {self.refresh_rate}")
        if self.buffer_duration <= 0:
            raise ValueError(f"Invalid buffer duration: {self.buffer_duration}")

        # Check display size limits (max 1015 dots per axis)
        total_panels = self.columns * self.rows
        if total_panels > 144:  # Conservative limit for reasonable configurations
            raise ValueError(f"Too many panels: {total_panels} (max 144 for stability)")

        # Get panel dimensions based on panel type
        panel_width, panel_height = self._get_panel_dimensions()

        # Calculate total canvas size
        canvas_width = panel_width * self.columns
        canvas_height = panel_height * self.rows

        if canvas_width > 1015 or canvas_height > 1015:
            raise ValueError(
                f"Canvas size {canvas_width}x{canvas_height} exceeds maximum 1015x1015 dots"
            )

        # Set computed canvas size
        object.__setattr__(self, "canvas_size", Size(canvas_width, canvas_height))

        # Generate panel configurations in grid layout
        panels = []
        address = 0

        for row in range(self.rows):
            for col in range(self.columns):
                panel_id = f"panel_{row}_{col}"
                origin_x = col * panel_width
                origin_y = row * panel_height

                panel = PanelConfig(
                    id=panel_id,
                    origin=Point(origin_x, origin_y),
                    size=Size(panel_width, panel_height),
                    address=address,
                    enabled=True,
                )
                panels.append(panel)
                address += 1

        # Set computed panels list
        object.__setattr__(self, "panels", panels)

    def _get_panel_dimensions(self) -> tuple[int, int]:
        """Get panel width and height from panel type."""
        if self.panel_type == DataBytes.BYTES_7:
            return (7, 7)  # 7x7 panels
        elif self.panel_type == DataBytes.BYTES_14:
            return (14, 7)  # 14x7 panels
        elif self.panel_type == DataBytes.BYTES_28:
            return (28, 7)  # 28x7 panels
        else:
            raise ValueError(f"Unknown panel type: {self.panel_type}")

    @property
    def enabled_panels(self) -> List[PanelConfig]:
        """Get list of enabled panels."""
        return [p for p in self.panels if p.enabled]

    @property
    def panel_count(self) -> int:
        """Get count of enabled panels."""
        return len(self.enabled_panels)

    def get_panel_by_id(self, panel_id: str) -> Optional[PanelConfig]:
        """Get panel configuration by ID."""
        for panel in self.panels:
            if panel.id == panel_id:
                return panel
        return None

    def get_panel_by_address(self, address: int) -> Optional[PanelConfig]:
        """Get panel configuration by RS-485 address."""
        for panel in self.enabled_panels:
            if panel.address == address:
                return panel
        return None

    def get_canvas_coverage(self) -> float:
        """Calculate what percentage of canvas is covered by panels."""
        if self.canvas_size.w == 0 or self.canvas_size.h == 0:
            return 0.0

        total_canvas_pixels = self.canvas_size.w * self.canvas_size.h
        covered_pixels = sum(p.size.w * p.size.h for p in self.enabled_panels)

        return min(covered_pixels / total_canvas_pixels, 1.0)


def load_config_from_toml(config_path: str | Path) -> DisplayConfig:
    """
    Load display configuration from a TOML file with simplified grid-based format.

    Args:
        config_path: Path to the TOML configuration file

    Returns:
        DisplayConfig: Loaded and validated configuration

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If configuration is invalid
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    logger.info(f"Loading configuration from {config_path}")

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        # Parse display settings
        display_data = data.get("display", {})
        if not display_data:
            raise ValueError("Missing [display] section in configuration")

        # Parse panel type
        panel_type_str = display_data.get("panel_type")
        if not panel_type_str:
            raise ValueError("Missing 'panel_type' in [display] section")

        # Convert panel type string to DataBytes enum
        panel_type_map = {
            "7x7": DataBytes.BYTES_7,
            "14x7": DataBytes.BYTES_14,
            "28x7": DataBytes.BYTES_28,
        }
        panel_type = panel_type_map.get(panel_type_str)
        if panel_type is None:
            valid_types = ", ".join(panel_type_map.keys())
            raise ValueError(
                f"Invalid panel_type '{panel_type_str}'. Valid types: {valid_types}"
            )

        # Parse grid dimensions
        columns = display_data.get("columns")
        rows = display_data.get("rows")
        if columns is None or rows is None:
            raise ValueError("Missing 'columns' and/or 'rows' in [display] section")

        # Parse serial config
        serial_data = data.get("serial", {})
        serial_config = SerialConfig(
            port=serial_data.get("port", "/dev/ttyUSB0"),
            baudrate=serial_data.get("baudrate", 9600),
            timeout=serial_data.get("timeout", 1.0),
            mock=serial_data.get("mock", False),
        )

        # Create display config (canvas_size and panels will be auto-generated)
        config = DisplayConfig(
            panel_type=panel_type,
            columns=columns,
            rows=rows,
            serial=serial_config,
            refresh_rate=display_data.get("refresh_rate", 30.0),
            buffer_duration=display_data.get("buffer_duration", 0.5),
        )

        logger.info(
            f"Loaded configuration: {config.panel_count} panels, "
            f"{config.canvas_size.w}×{config.canvas_size.h} canvas, "
            f"{config.refresh_rate}fps"
        )

        return config

    except Exception as e:
        logger.error(f"Failed to load configuration from {config_path}: {e}")
        raise ValueError(f"Invalid configuration: {e}") from e


def create_default_single_panel_config() -> DisplayConfig:
    """Create default configuration for a single 28×7 panel."""
    serial_config = SerialConfig(
        port="/dev/ttyUSB0",
        baudrate=9600,
        timeout=1.0,
        mock=True,  # Default to mock for safety
    )

    return DisplayConfig(
        panel_type=DataBytes.BYTES_28,  # 28x7 panels
        columns=1,
        rows=1,
        serial=serial_config,
        refresh_rate=30.0,
        buffer_duration=0.5,
    )


def create_stacked_panels_config() -> DisplayConfig:
    """Create configuration for two 28×7 panels stacked vertically (28×14 display)."""
    serial_config = SerialConfig(
        port="/dev/ttyUSB0", baudrate=9600, timeout=1.0, mock=True
    )

    return DisplayConfig(
        panel_type=DataBytes.BYTES_28,  # 28x7 panels
        columns=1,
        rows=2,  # Stacked vertically
        serial=serial_config,
        refresh_rate=30.0,
        buffer_duration=0.5,
    )


def create_side_by_side_panels_config() -> DisplayConfig:
    """Create configuration for two 7×28 panels side by side (7×56 display)."""
    panels = [
        PanelConfig(
            id="left",
            origin=Point(0, 0),
            size=Size(28, 7),
            orientation="normal",
            address=0,
            enabled=True,
        ),
        PanelConfig(
            id="right",
            origin=Point(28, 0),
            size=Size(28, 7),
            orientation="normal",
            address=1,
            enabled=True,
        ),
    ]

    serial_config = SerialConfig(
        port="/dev/ttyUSB0", baudrate=9600, timeout=1.0, mock=True
    )

    return DisplayConfig(
        canvas_size=Size(56, 7),
        panels=panels,
        serial=serial_config,
        refresh_rate=30.0,
        buffer_duration=0.5,
    )
