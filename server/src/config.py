from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Literal

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
            Point(self.origin.x + self.size.w, self.origin.y + self.size.h)
        )
    
    def overlaps_with(self, other: PanelConfig) -> bool:
        """Check if this panel overlaps with another panel."""
        self_tl, self_br = self.bounds
        other_tl, other_br = other.bounds
        
        return not (
            self_br.x <= other_tl.x or  # self is to the left of other
            other_br.x <= self_tl.x or  # other is to the left of self
            self_br.y <= other_tl.y or  # self is above other
            other_br.y <= self_tl.y     # other is above self
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
    Complete display configuration including panel layout and settings.
    
    Attributes:
        canvas_size: Overall canvas dimensions (width, height)
        panels: List of panel configurations
        serial: Serial communication settings
        refresh_rate: Target refresh rate in FPS
        buffer_duration: Frame buffer duration in seconds
    """
    canvas_size: Size
    panels: List[PanelConfig]
    serial: SerialConfig
    refresh_rate: float = 30.0
    buffer_duration: float = 0.5
    
    def __post_init__(self):
        """Validate display configuration."""
        if self.canvas_size.w <= 0 or self.canvas_size.h <= 0:
            raise ValueError(f"Invalid canvas size: {self.canvas_size}")
        
        if self.refresh_rate <= 0 or self.refresh_rate > 30:
            raise ValueError(f"Invalid refresh rate: {self.refresh_rate}")
        
        if self.buffer_duration <= 0:
            raise ValueError(f"Invalid buffer duration: {self.buffer_duration}")
        
        # Validate panels
        if not self.panels:
            raise ValueError("At least one panel must be configured")
        
        # Check for duplicate panel IDs
        panel_ids = [p.id for p in self.panels]
        if len(panel_ids) != len(set(panel_ids)):
            raise ValueError("Panel IDs must be unique")
        
        # Check for duplicate addresses
        addresses = [p.address for p in self.panels if p.enabled]
        if len(addresses) != len(set(addresses)):
            raise ValueError("Panel addresses must be unique")
        
        # Check for overlapping panels
        for i, panel1 in enumerate(self.panels):
            if not panel1.enabled:
                continue
            for panel2 in self.panels[i + 1:]:
                if not panel2.enabled:
                    continue
                if panel1.overlaps_with(panel2):
                    raise ValueError(f"Panels {panel1.id} and {panel2.id} overlap")
        
        # Check that all panels fit within canvas
        for panel in self.panels:
            if not panel.enabled:
                continue
            _, bottom_right = panel.bounds
            if (bottom_right.x > self.canvas_size.w or 
                bottom_right.y > self.canvas_size.h):
                raise ValueError(f"Panel {panel.id} extends beyond canvas bounds")
    
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
    Load display configuration from a TOML file.
    
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
        
        # Parse canvas size
        canvas_data = data.get("canvas", {})
        canvas_size = Size(
            w=canvas_data.get("width", 28),
            h=canvas_data.get("height", 7)
        )
        
        # Parse serial config
        serial_data = data.get("serial", {})
        serial_config = SerialConfig(
            port=serial_data.get("port", "/dev/ttyUSB0"),
            baudrate=serial_data.get("baudrate", 9600),
            timeout=serial_data.get("timeout", 1.0),
            mock=serial_data.get("mock", False)
        )
        
        # Parse panels
        panels_data = data.get("panels", [])
        if not panels_data:
            raise ValueError("No panels configured")
        
        panels = []
        for panel_data in panels_data:
            origin_data = panel_data.get("origin", {})
            size_data = panel_data.get("size", {})
            
            panel = PanelConfig(
                id=panel_data.get("id", ""),
                origin=Point(
                    x=origin_data.get("x", 0),
                    y=origin_data.get("y", 0)
                ),
                size=Size(
                    w=size_data.get("width", 28),
                    h=size_data.get("height", 7)
                ),
                orientation=panel_data.get("orientation", "normal"),
                address=panel_data.get("address", 0),
                enabled=panel_data.get("enabled", True)
            )
            panels.append(panel)
        
        # Parse display settings
        display_data = data.get("display", {})
        config = DisplayConfig(
            canvas_size=canvas_size,
            panels=panels,
            serial=serial_config,
            refresh_rate=display_data.get("refresh_rate", 30.0),
            buffer_duration=display_data.get("buffer_duration", 0.5)
        )
        
        logger.info(f"Loaded configuration: {config.panel_count} panels, "
                   f"{config.canvas_size.w}×{config.canvas_size.h} canvas, "
                   f"{config.refresh_rate}fps")
        
        return config
        
    except Exception as e:
        logger.error(f"Failed to load configuration from {config_path}: {e}")
        raise ValueError(f"Invalid configuration: {e}") from e


def create_default_single_panel_config() -> DisplayConfig:
    """Create default configuration for a single 7×28 panel."""
    panel = PanelConfig(
        id="main",
        origin=Point(0, 0),
        size=Size(28, 7),
        orientation="normal",
        address=0,
        enabled=True
    )
    
    serial_config = SerialConfig(
        port="/dev/ttyUSB0",
        baudrate=9600,
        timeout=1.0,
        mock=True  # Default to mock for safety
    )
    
    return DisplayConfig(
        canvas_size=Size(28, 7),
        panels=[panel],
        serial=serial_config,
        refresh_rate=30.0,
        buffer_duration=0.5
    )


def create_stacked_panels_config() -> DisplayConfig:
    """Create configuration for two 7×28 panels stacked vertically (14×28 display)."""
    panels = [
        PanelConfig(
            id="top",
            origin=Point(0, 0),
            size=Size(28, 7),
            orientation="normal",
            address=0,
            enabled=True
        ),
        PanelConfig(
            id="bottom", 
            origin=Point(0, 7),
            size=Size(28, 7),
            orientation="normal",
            address=1,
            enabled=True
        )
    ]
    
    serial_config = SerialConfig(
        port="/dev/ttyUSB0",
        baudrate=9600,
        timeout=1.0,
        mock=True
    )
    
    return DisplayConfig(
        canvas_size=Size(28, 14),
        panels=panels,
        serial=serial_config,
        refresh_rate=30.0,
        buffer_duration=0.5
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
            enabled=True
        ),
        PanelConfig(
            id="right",
            origin=Point(28, 0),
            size=Size(28, 7),
            orientation="normal",
            address=1,
            enabled=True
        )
    ]
    
    serial_config = SerialConfig(
        port="/dev/ttyUSB0",
        baudrate=9600,
        timeout=1.0,
        mock=True
    )
    
    return DisplayConfig(
        canvas_size=Size(56, 7),
        panels=panels,
        serial=serial_config,
        refresh_rate=30.0,
        buffer_duration=0.5
    )