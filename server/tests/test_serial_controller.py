"""Tests for serial controller and panel mapping."""

import pytest
import numpy as np
import asyncio

from src.config import create_default_single_panel_config, create_stacked_panels_config
from src.serial_controller import SerialController
from src.panel_mapper import create_test_pattern, update_panels


@pytest.fixture
def single_panel_config():
    """Single panel configuration for testing."""
    return create_default_single_panel_config()


@pytest.fixture
def stacked_config():
    """Stacked panels configuration for testing."""  
    return create_stacked_panels_config()


@pytest.fixture
def mock_controller(single_panel_config):
    """Create mock serial controller for testing."""
    return SerialController(single_panel_config, use_hardware=False)


@pytest.mark.asyncio
async def test_serial_controller_initialization(mock_controller, single_panel_config):
    """Test serial controller initializes correctly."""
    assert mock_controller.config == single_panel_config
    assert not mock_controller.is_connected()
    
    # Test panel lookup
    panel = mock_controller.get_panel_by_address(0)
    assert panel is not None
    assert panel.id == "main"
    assert panel.size.w == 28
    assert panel.size.h == 7


@pytest.mark.asyncio
async def test_mock_connection(mock_controller):
    """Test mock serial connection."""
    # Should not be connected initially
    assert not mock_controller.is_connected()
    
    # Connect should succeed
    success = await mock_controller.connect()
    assert success is True
    assert mock_controller.is_connected()
    
    # Disconnect
    await mock_controller.disconnect()
    assert not mock_controller.is_connected()


@pytest.mark.asyncio
async def test_send_panel_frame(mock_controller):
    """Test sending frame to individual panel."""
    await mock_controller.connect()
    
    # Create test frame data (7x28 for single panel)
    frame_data = np.zeros((7, 28), dtype=bool)
    frame_data[0, :] = True  # Top row on
    frame_data[-1, :] = True  # Bottom row on
    
    # Send to panel address 0
    success = await mock_controller.send_panel_frame(0, frame_data)
    assert success is True
    
    # Test invalid panel address
    success = await mock_controller.send_panel_frame(99, frame_data)
    assert success is False
    
    # Test invalid frame dimensions
    wrong_size_data = np.zeros((5, 20), dtype=bool)
    success = await mock_controller.send_panel_frame(0, wrong_size_data)
    assert success is False


@pytest.mark.asyncio
async def test_send_canvas_frame_single_panel(mock_controller, single_panel_config):
    """Test sending full canvas frame to single panel."""
    await mock_controller.connect()
    
    # Create test pattern
    canvas_bits = create_test_pattern(single_panel_config, "checkerboard")
    
    # Send canvas frame
    success = await mock_controller.send_canvas_frame(canvas_bits)
    assert success is True
    
    # Test with invalid canvas size
    wrong_size_bits = b'\x00' * 10  # Too small for 28x7 canvas
    success = await mock_controller.send_canvas_frame(wrong_size_bits)
    assert success is False


@pytest.mark.asyncio
async def test_send_canvas_frame_stacked_panels():
    """Test sending canvas frame to multiple stacked panels."""
    stacked_config = create_stacked_panels_config()
    controller = SerialController(stacked_config, use_hardware=False)
    
    await controller.connect()
    
    # Create test pattern for 14x28 canvas (two panels stacked)
    canvas_bits = create_test_pattern(stacked_config, "border")
    
    success = await controller.send_canvas_frame(canvas_bits)
    assert success is True
    
    await controller.disconnect()


@pytest.mark.asyncio
async def test_send_test_patterns(mock_controller):
    """Test sending built-in test patterns."""
    await mock_controller.connect()
    
    # Test each pattern type
    patterns = ["checkerboard", "border", "solid", "gradient"]
    
    for pattern in patterns:
        success = await mock_controller.send_test_pattern(pattern)
        assert success is True, f"Failed to send {pattern} pattern"
    
    # Test invalid pattern
    success = await mock_controller.send_test_pattern("invalid_pattern")
    assert success is True  # Should fall back to checkerboard


def test_panel_mapper_single_panel(single_panel_config):
    """Test panel mapping for single panel."""
    # Create test canvas
    canvas_bits = create_test_pattern(single_panel_config, "checkerboard")
    
    # Map to panel data
    panel_data = update_panels(
        canvas_bits,
        single_panel_config.canvas_size.w,
        single_panel_config.canvas_size.h,
        single_panel_config
    )
    
    # Should have data for one panel (address 0)
    assert len(panel_data) == 1
    assert 0 in panel_data
    
    # Check data size is correct for 7x28 panel
    panel_bytes = panel_data[0]
    # Panel mapper pads to multiple of 8 columns: 28 -> 32, so 7 rows * 4 bytes = 28 bytes
    expected_bytes = 7 * ((28 + 7) // 8)  # 7 rows * 4 bytes per row = 28 bytes
    assert len(panel_bytes) == expected_bytes


def test_panel_mapper_stacked_panels():
    """Test panel mapping for stacked panels."""
    stacked_config = create_stacked_panels_config()
    
    # Create test pattern for full 14x28 canvas
    canvas_bits = create_test_pattern(stacked_config, "solid")
    
    # Map to panel data
    panel_data = update_panels(
        canvas_bits,
        stacked_config.canvas_size.w,
        stacked_config.canvas_size.h,
        stacked_config
    )
    
    # Should have data for two panels
    assert len(panel_data) == 2
    assert 0 in panel_data  # Top panel
    assert 1 in panel_data  # Bottom panel
    
    # Both panels should have same data size
    for address in [0, 1]:
        panel_bytes = panel_data[address]
        # Each panel: 7 rows * 4 bytes per row (28 cols padded to 32) = 28 bytes
        expected_bytes = 7 * ((28 + 7) // 8)
        assert len(panel_bytes) == expected_bytes


def test_canvas_test_patterns(single_panel_config):
    """Test different test pattern generation."""
    patterns = {
        "checkerboard": lambda canvas: canvas[0, 0] != canvas[0, 1],  # Should alternate
        "border": lambda canvas: np.all(canvas[0, :]) and np.all(canvas[:, 0]),  # Borders on
        "solid": lambda canvas: np.all(canvas),  # All pixels on
        "gradient": lambda canvas: np.any(canvas)  # Some pixels on
    }
    
    from src.panel_mapper import unpack_canvas_from_bytes
    
    for pattern_name, test_func in patterns.items():
        canvas_bits = create_test_pattern(single_panel_config, pattern_name)
        
        # Unpack to verify pattern
        canvas_array = unpack_canvas_from_bytes(
            canvas_bits,
            single_panel_config.canvas_size.w,
            single_panel_config.canvas_size.h
        )
        
        # Apply pattern-specific test
        assert test_func(canvas_array), f"Pattern {pattern_name} failed validation"


@pytest.mark.asyncio
async def test_controller_stats(mock_controller):
    """Test getting controller statistics."""
    await mock_controller.connect()
    
    stats = mock_controller.get_display_stats()
    
    # Check required fields
    assert 'canvas_size' in stats
    assert 'panel_count' in stats  
    assert 'panels' in stats
    assert 'connected' in stats
    assert 'serial_config' in stats
    
    # Check values
    assert stats['panel_count'] == 1
    assert stats['connected'] is True
    assert stats['canvas_size'] == "28x7"
    
    # Check panel info
    assert len(stats['panels']) == 1
    panel_info = stats['panels'][0]
    assert panel_info['id'] == 'main'
    assert panel_info['address'] == 0


def test_controller_helper_methods(mock_controller):
    """Test controller helper methods."""
    # Test dimensions
    height, width = mock_controller.get_canvas_dimensions()
    assert height == 7
    assert width == 28
    
    # Test panel addresses
    addresses = mock_controller.get_enabled_panel_addresses()
    assert addresses == [0]
    
    # Test panel lookup
    panel = mock_controller.get_panel_by_address(0)
    assert panel.id == "main"
    
    # Test invalid address
    invalid_panel = mock_controller.get_panel_by_address(99)
    assert invalid_panel is None


if __name__ == "__main__":
    pytest.main([__file__])