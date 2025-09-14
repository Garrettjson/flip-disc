"""Configuration for flip-disc display."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .exceptions import ConfigurationError


@dataclass
class SerialConfig:
    """Serial port configuration."""

    port: str = "/dev/ttyUSB0"
    baudrate: int = 9600
    timeout: float = 1.0
    mock: bool = True


@dataclass
class DisplayConfig:
    """Display configuration with TOML support."""

    # Display dimensions
    width: int = 112
    height: int = 56
    refresh_rate: float = 20.0
    buffer_duration: float = 0.5

    # Serial configuration
    serial: SerialConfig = None

    # Panel grid configuration
    panel_w: int = 28
    panel_h: int = 7
    columns: int = 4
    rows: int = 8
    address_base: int = 1

    def __post_init__(self):
        if self.serial is None:
            self.serial = SerialConfig()

        # Validation
        if self.width <= 0 or self.height <= 0:
            raise ConfigurationError(
                f"Display dimensions must be positive: {self.width}x{self.height}"
            )
        if self.refresh_rate <= 0:
            raise ConfigurationError(
                f"Refresh rate must be positive: {self.refresh_rate}"
            )
        if self.buffer_duration <= 0:
            raise ConfigurationError(
                f"Buffer duration must be positive: {self.buffer_duration}"
            )

        # Ensure panel settings are positive
        if self.panel_w <= 0 or self.panel_h <= 0:
            raise ConfigurationError(
                f"Panel dimensions must be positive: {self.panel_w}x{self.panel_h}"
            )
        if self.columns <= 0 or self.rows <= 0:
            raise ConfigurationError(
                f"Panel grid must be positive: {self.columns}x{self.rows}"
            )

        # Keep width/height consistent with panel grid
        expected_w = self.panel_w * self.columns
        expected_h = self.panel_h * self.rows
        # If provided width/height differ, prefer panel grid to derive canvas size
        self.width = expected_w
        self.height = expected_h


def default_config() -> DisplayConfig:
    """Return default config for development."""
    return DisplayConfig()


def load_config(config_path: str | None = None) -> DisplayConfig:
    """Load config from TOML file or return default."""
    if config_path is None:
        # Look for default config files
        for path in ["config.toml", "flipdisc.toml"]:
            if Path(path).exists():
                config_path = path
                break
        else:
            # No config file found, use defaults
            return default_config()

    config_file = Path(config_path)
    if not config_file.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")

    try:
        with config_file.open("rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        raise ConfigurationError(f"Failed to parse TOML config: {e}") from e

    return _parse_config(data)


def _parse_config(data: dict) -> DisplayConfig:
    """Parse TOML data into DisplayConfig."""
    try:
        display_section = data.get("display", {})
        serial_section = data.get("serial", {})

        # Handle panel-based configuration
        panel_type = display_section.get("panel_type", "28x7")
        columns = display_section.get("columns", 4)
        rows = display_section.get("rows", 2)

        # Parse panel dimensions
        try:
            panel_w, panel_h = map(int, panel_type.split("x"))
        except ValueError as e:
            raise ConfigurationError(f"Invalid panel_type format: {panel_type}") from e

        # Calculate total dimensions
        width = panel_w * columns
        height = panel_h * rows

        # Build serial config
        serial_config = SerialConfig(
            port=serial_section.get("port", "/dev/ttyUSB0"),
            baudrate=serial_section.get("baudrate", 9600),
            timeout=serial_section.get("timeout", 1.0),
            mock=serial_section.get("mock", True),
        )

        return DisplayConfig(
            width=width,
            height=height,
            refresh_rate=display_section.get("refresh_rate", 20.0),
            buffer_duration=display_section.get("buffer_duration", 0.5),
            serial=serial_config,
            panel_w=panel_w,
            panel_h=panel_h,
            columns=columns,
            rows=rows,
            address_base=display_section.get("address_base", 1),
        )

    except KeyError as e:
        raise ConfigurationError(f"Missing required config key: {e}") from e
    except (ValueError, TypeError) as e:
        raise ConfigurationError(f"Invalid config value: {e}") from e
