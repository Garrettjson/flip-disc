"""Tests for configuration loading and validation."""

import pytest
import tempfile
from pathlib import Path

from src.config import (
    DisplayConfig, 
    PanelConfig, 
    SerialConfig,
    Point, 
    Size,
    load_config_from_toml,
    create_default_single_panel_config,
    create_stacked_panels_config
)


def test_default_single_panel_config():
    """Test creating default single panel configuration."""
    config = create_default_single_panel_config()
    
    assert config.canvas_size.w == 28
    assert config.canvas_size.h == 7
    assert config.panel_count == 1
    assert len(config.enabled_panels) == 1
    
    panel = config.enabled_panels[0]
    assert panel.id == "main"
    assert panel.address == 0
    assert panel.origin.x == 0
    assert panel.origin.y == 0
    assert panel.size.w == 28
    assert panel.size.h == 7
    assert panel.orientation == "normal"
    assert panel.enabled is True
    
    # Test serial config defaults
    assert config.serial.mock is True  # Default to mock for safety
    assert config.serial.port == "/dev/ttyUSB0"
    assert config.serial.baudrate == 9600


def test_stacked_panels_config():
    """Test creating stacked panels configuration."""
    config = create_stacked_panels_config()
    
    assert config.canvas_size.w == 28
    assert config.canvas_size.h == 14  # Two 7-high panels stacked
    assert config.panel_count == 2
    assert len(config.enabled_panels) == 2
    
    # Test top panel
    top_panel = config.get_panel_by_id("top")
    assert top_panel is not None
    assert top_panel.address == 0
    assert top_panel.origin.y == 0
    
    # Test bottom panel  
    bottom_panel = config.get_panel_by_id("bottom")
    assert bottom_panel is not None
    assert bottom_panel.address == 1
    assert bottom_panel.origin.y == 7
    
    # Test no overlapping panels (validation should pass)
    assert config.get_canvas_coverage() > 0.99  # Should cover full canvas


def test_config_validation():
    """Test configuration validation catches errors."""
    
    # Test overlapping panels
    with pytest.raises(ValueError, match="overlap"):
        overlapping_panels = [
            PanelConfig("panel1", Point(0, 0), Size(20, 7), address=0),
            PanelConfig("panel2", Point(10, 0), Size(20, 7), address=1)  # Overlaps with panel1
        ]
        DisplayConfig(Size(40, 7), overlapping_panels, SerialConfig())
    
    # Test duplicate addresses
    with pytest.raises(ValueError, match="addresses must be unique"):
        duplicate_addr_panels = [
            PanelConfig("panel1", Point(0, 0), Size(14, 7), address=0),
            PanelConfig("panel2", Point(14, 0), Size(14, 7), address=0)  # Same address
        ]
        DisplayConfig(Size(28, 7), duplicate_addr_panels, SerialConfig())
    
    # Test panel extending beyond canvas
    with pytest.raises(ValueError, match="extends beyond canvas bounds"):
        oversized_panel = [
            PanelConfig("big", Point(0, 0), Size(50, 7), address=0)  # Bigger than 28x7 canvas
        ]
        DisplayConfig(Size(28, 7), oversized_panel, SerialConfig())


def test_load_config_from_toml():
    """Test loading configuration from TOML file."""
    
    # Create temporary TOML config
    toml_content = '''
[canvas]
width = 28
height = 14

[display]
refresh_rate = 25.0
buffer_duration = 0.6

[serial]
port = "/dev/ttyUSB1"
baudrate = 19200
mock = false

[[panels]]
id = "top"
address = 0
enabled = true
[panels.origin]
x = 0
y = 0
[panels.size]
width = 28
height = 7
orientation = "normal"

[[panels]]
id = "bottom"
address = 1
enabled = true
[panels.origin]
x = 0
y = 7
[panels.size]
width = 28
height = 7
orientation = "normal"
'''
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
        f.write(toml_content)
        temp_path = f.name
    
    try:
        config = load_config_from_toml(temp_path)
        
        # Test canvas
        assert config.canvas_size.w == 28
        assert config.canvas_size.h == 14
        
        # Test display settings
        assert config.refresh_rate == 25.0
        assert config.buffer_duration == 0.6
        
        # Test serial settings
        assert config.serial.port == "/dev/ttyUSB1"
        assert config.serial.baudrate == 19200
        assert config.serial.mock is False
        
        # Test panels
        assert config.panel_count == 2
        top_panel = config.get_panel_by_id("top")
        bottom_panel = config.get_panel_by_id("bottom")
        
        assert top_panel.address == 0
        assert bottom_panel.address == 1
        assert bottom_panel.origin.y == 7
        
    finally:
        Path(temp_path).unlink()  # Clean up temp file


def test_config_file_not_found():
    """Test handling of missing config file."""
    with pytest.raises(FileNotFoundError):
        load_config_from_toml("/nonexistent/config.toml")


def test_panel_bounds_calculation():
    """Test panel bounds calculation."""
    panel = PanelConfig("test", Point(10, 5), Size(20, 7), address=0)
    
    top_left, bottom_right = panel.bounds
    assert top_left.x == 10
    assert top_left.y == 5
    assert bottom_right.x == 30  # 10 + 20
    assert bottom_right.y == 12  # 5 + 7


def test_panel_overlap_detection():
    """Test panel overlap detection."""
    panel1 = PanelConfig("p1", Point(0, 0), Size(10, 10), address=0)
    panel2 = PanelConfig("p2", Point(5, 5), Size(10, 10), address=1)  # Overlaps
    panel3 = PanelConfig("p3", Point(15, 0), Size(10, 10), address=2)  # No overlap
    
    assert panel1.overlaps_with(panel2) is True
    assert panel1.overlaps_with(panel3) is False
    assert panel2.overlaps_with(panel3) is False


if __name__ == "__main__":
    pytest.main([__file__])