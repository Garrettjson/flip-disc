"""Tests for configuration loading and cross-cutting validation."""

import pytest
import tempfile
from pathlib import Path

from src.config import (
    DisplayConfig,
    PanelConfig,
    SerialConfig,
    Point,
    Size,
    load_from_toml,
)
from src.validation import (
    validate_display_config,
    PanelValidationError,
    CanvasValidationError,
)


def test_load_simple_schema_from_toml():
    """Load simplified [display] schema with auto-generated panels."""
    toml_content = """
[display]
panel_type = "28x7"
columns = 2
rows = 1
refresh_rate = 25.0
buffer_duration = 0.6

[serial]
port = "/dev/ttyUSB1"
baudrate = 19200
mock = false
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(toml_content)
        path = f.name

    try:
        cfg = load_from_toml(path)
        assert cfg.canvas_size.w == 56
        assert cfg.canvas_size.h == 7
        assert len(cfg.panels) == 2
        assert cfg.refresh_rate == 25.0
        assert cfg.buffer_duration == 0.6
        assert cfg.serial.port == "/dev/ttyUSB1"
        assert cfg.serial.baudrate == 19200
        assert cfg.serial.mock is False
    finally:
        Path(path).unlink()


def test_validation_duplicate_addresses():
    panels = [
        PanelConfig("p1", Point(0, 0), Size(14, 7), address=0),
        PanelConfig("p2", Point(14, 0), Size(14, 7), address=0),
    ]
    cfg = DisplayConfig(Size(28, 7), panels, SerialConfig())
    with pytest.raises(PanelValidationError):
        validate_display_config(cfg)


def test_validation_out_of_bounds():
    # Use supported size but place panel so it exceeds canvas bounds
    panels = [
        PanelConfig("p1", Point(1, 0), Size(28, 7), address=0),  # x + w = 29 > 28
    ]
    cfg = DisplayConfig(Size(28, 7), panels, SerialConfig())
    with pytest.raises(CanvasValidationError):
        validate_display_config(cfg)


def test_validation_mixed_panel_widths():
    panels = [
        PanelConfig("p1", Point(0, 0), Size(14, 7), address=0),
        PanelConfig("p2", Point(14, 0), Size(28, 7), address=1),
    ]
    cfg = DisplayConfig(Size(42, 7), panels, SerialConfig())
    with pytest.raises(PanelValidationError):
        validate_display_config(cfg)


if __name__ == "__main__":
    pytest.main([__file__])
