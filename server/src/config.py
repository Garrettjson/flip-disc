# server/src/config.py
from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Literal

from .protocol_config import DataBytes, Refresh, ProtocolConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Point:
    x: int
    y: int

    def __post_init__(self) -> None:
        if self.x < 0 or self.y < 0:
            raise ValueError(f"Point must be non-negative, got ({self.x},{self.y})")


@dataclass(frozen=True)
class Size:
    w: int
    h: int

    def __post_init__(self) -> None:
        if self.w <= 0 or self.h <= 0:
            raise ValueError(f"Size must be positive, got ({self.w}x{self.h})")


Orientation = Literal["normal", "rot90", "rot180", "rot270"]


@dataclass(frozen=True)
class PanelConfig:
    id: str
    origin: Point
    size: Size
    orientation: Orientation = "normal"
    address: int = 0

    def __post_init__(self) -> None:
        if not (0 <= self.address <= 0xFF):
            raise ValueError(
                f"Panel '{self.id}' address must be 0-255, got {self.address}"
            )

        orient = (self.orientation or "normal").lower()
        if orient not in {"normal", "rot90", "rot180", "rot270"}:
            raise ValueError(
                f"Panel '{self.id}' has invalid orientation '{self.orientation}'"
            )


@dataclass(frozen=True)
class SerialConfig:
    port: str = "/dev/ttyUSB0"
    baudrate: int = 9600
    timeout: float = 1.0
    mock: bool = True

    def __post_init__(self) -> None:
        if self.baudrate <= 0:
            raise ValueError("Serial baudrate must be > 0")
        if self.timeout <= 0:
            raise ValueError("Serial timeout must be > 0")


@dataclass(frozen=True)
class DisplayConfig:
    canvas_size: Size
    panels: List[PanelConfig]
    serial: SerialConfig = field(default_factory=SerialConfig)
    refresh_rate: float = 20.0
    buffer_duration: float = 0.5

    @property
    def protocol_service(self):
        """Get the protocol service for this display configuration."""
        from .protocol_service import DisplayProtocolService

        return DisplayProtocolService(self)

    @property
    def data_bytes(self) -> DataBytes:
        """Return the per-panel data width in bytes used by protocol."""
        return self.protocol_service.get_data_bytes()

    @property
    def refresh_mode(self) -> Refresh:
        """Determine refresh mode based on panel count."""
        return self.protocol_service.get_refresh_mode()

    @property
    def protocol_config(self) -> ProtocolConfig:
        """Get the complete protocol configuration for this display."""
        return self.protocol_service.get_protocol_config()

    def validate_within_canvas(self) -> None:
        from .validation import validate_display_config

        validate_display_config(self)


def _parse_orientation(orient: Optional[str]) -> Orientation:
    orient = (orient or "normal").lower()
    if orient not in {"normal", "rot90", "rot180", "rot270"}:
        raise ValueError(f"Invalid orientation '{orient}' in config file")
    return orient  # type: ignore[return-value]


def _load_panel(entry: dict) -> PanelConfig:
    # Accept both nested dicts and flat values for origin/size
    origin = entry.get("origin") or {}
    size = entry.get("size") or {}
    return PanelConfig(
        id=str(entry["id"]),
        origin=Point(int(origin.get("x", 0)), int(origin.get("y", 0))),
        size=Size(int(size.get("w", 0)), int(size.get("h", 0))),
        orientation=_parse_orientation(entry.get("orientation")),
        address=int(entry.get("address", 0)),
    )


def load_from_toml(config_path: str | Path) -> DisplayConfig:
    """
    Load a DisplayConfig from a TOML file.

    Expected TOML structure:

    [canvas]
    w = 56
    h = 7

    [[panels]]
    id = "left"
    origin = { x = 0, y = 0 }
    size   = { w = 28, h = 7 }
    orientation = "normal"  # normal|rot90|rot180|rot270|cw|ccw
    address = 0

    [[panels]]
    id = "right"
    origin = { x = 28, y = 0 }
    size   = { w = 28, h = 7 }
    address = 1

    [serial]
    port = "/dev/ttyUSB0"
    baudrate = 9600
    timeout = 1.0
    mock = true

    [runtime]
    refresh_rate = 20.0
    buffer_duration = 0.5
    """
    p = Path(config_path)
    if not p.exists():
        raise FileNotFoundError(f"Configuration file not found: {p}")

    with p.open("rb") as f:
        data = tomllib.load(f)

    serial = data.get("serial") or {}

    # Support both explicit [[panels]] schema and simplified [display] grid schema
    if "canvas" in data or "panels" in data or "runtime" in data:
        canvas = data.get("canvas") or {}
        panels = data.get("panels") or []
        runtime = data.get("runtime") or {}

        cfg = DisplayConfig(
            canvas_size=Size(int(canvas.get("w", 56)), int(canvas.get("h", 7))),
            panels=[_load_panel(e) for e in panels],
            serial=SerialConfig(
                port=str(serial.get("port", "/dev/ttyUSB0")),
                baudrate=int(serial.get("baudrate", 9600)),
                timeout=float(serial.get("timeout", 1.0)),
                mock=bool(serial.get("mock", True)),
            ),
            refresh_rate=float(runtime.get("refresh_rate", 20.0)),
            buffer_duration=float(runtime.get("buffer_duration", 0.5)),
        )
    else:
        # Simplified schema under [display]
        display = data.get("display") or {}
        panel_type = str(display.get("panel_type", "28x7")).lower()
        columns = int(display.get("columns", 1))
        rows = int(display.get("rows", 1))
        refresh_rate = float(display.get("refresh_rate", 20.0))
        buffer_duration = float(display.get("buffer_duration", 0.5))

        # Determine panel dimensions
        if panel_type not in {"7x7", "14x7", "28x7"}:
            raise ValueError(f"Unsupported panel_type '{panel_type}' in config")
        panel_w = int(panel_type.split("x")[0])
        panel_h = int(panel_type.split("x")[1])

        canvas_w = panel_w * columns
        canvas_h = panel_h * rows

        # Generate panels row-major with sequential addresses
        gen_panels: list[PanelConfig] = []
        addr = 0
        for r in range(rows):
            for c in range(columns):
                gen_panels.append(
                    PanelConfig(
                        id=f"panel_{r}_{c}",
                        origin=Point(c * panel_w, r * panel_h),
                        size=Size(panel_w, panel_h),
                        orientation="normal",
                        address=addr,
                    )
                )
                addr += 1

        cfg = DisplayConfig(
            canvas_size=Size(canvas_w, canvas_h),
            panels=gen_panels,
            serial=SerialConfig(
                port=str(serial.get("port", "/dev/ttyUSB0")),
                baudrate=int(serial.get("baudrate", 9600)),
                timeout=float(serial.get("timeout", 1.0)),
                mock=bool(serial.get("mock", True)),
            ),
            refresh_rate=refresh_rate,
            buffer_duration=buffer_duration,
        )

    # Early validations
    cfg.validate_within_canvas()
    _ = cfg.data_bytes
    _ = cfg.protocol_config  # Validate protocol configuration

    logger.info(
        "Loaded DisplayConfig: %s panels, canvas=%dx%d, serial=%s@%d (mock=%s)",
        len(cfg.panels),
        cfg.canvas_size.w,
        cfg.canvas_size.h,
        cfg.serial.port,
        cfg.serial.baudrate,
        cfg.serial.mock,
    )
    return cfg


def default_config() -> DisplayConfig:
    """A sensible local default: four 14x7 panels forming a 28x28 canvas."""
    panels = [
        PanelConfig(
            id="top_left",
            origin=Point(0, 0),
            size=Size(14, 7),
            orientation="normal",
            address=0,
        ),
        PanelConfig(
            id="top_right",
            origin=Point(14, 0),
            size=Size(14, 7),
            orientation="normal",
            address=1,
        ),
        PanelConfig(
            id="bottom_left",
            origin=Point(0, 7),
            size=Size(14, 7),
            orientation="normal",
            address=2,
        ),
        PanelConfig(
            id="bottom_right",
            origin=Point(14, 7),
            size=Size(14, 7),
            orientation="normal",
            address=3,
        ),
    ]

    cfg = DisplayConfig(
        canvas_size=Size(28, 28),
        panels=panels,
        serial=SerialConfig(port="/dev/ttyUSB0", baudrate=9600, timeout=1.0, mock=True),
        refresh_rate=20.0,
        buffer_duration=0.5,
    )
    cfg.validate_within_canvas()
    _ = cfg.data_bytes
    _ = cfg.protocol_config  # Validate protocol configuration
    return cfg
