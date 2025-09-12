"""Tests for frame buffer and credit system."""

import pytest
import asyncio
import time

from src.config import DisplayConfig, PanelConfig, SerialConfig, Point, Size
from src.frame_buffer import (
    AsyncFrameBuffer,
    Frame,
    create_frame_for_canvas,
    validate_frame_for_display,
)


@pytest.fixture
def display_config():
    """Create single-panel (28x7) display configuration for tests."""
    panel = PanelConfig("main", Point(0, 0), Size(28, 7), address=0)
    cfg = DisplayConfig(
        canvas_size=Size(28, 7),
        panels=[panel],
        serial=SerialConfig(mock=True),
        refresh_rate=30.0,
        buffer_duration=0.5,
    )
    cfg.validate_within_canvas()
    _ = cfg.protocol_config
    return cfg


@pytest.fixture
def frame_buffer(display_config):
    """Create frame buffer for tests."""
    return AsyncFrameBuffer(display_config)


@pytest.fixture
def sample_frame():
    """Create a sample frame for testing."""
    # Create canvas based on display_config defaults (avoid magic numbers)
    # Use fixed panel size for test inputs to keep tests self-contained
    PANEL_W = 28
    PANEL_H = 7
    stride = (PANEL_W + 7) // 8
    canvas_data = b"\x00" * (stride * PANEL_H)
    return Frame(
        frame_id=1, flags=0, width=28, height=7, data=canvas_data, timestamp=time.time()
    )


@pytest.mark.asyncio
async def test_frame_buffer_initialization(frame_buffer, display_config):
    """Test frame buffer initializes with correct parameters."""
    assert frame_buffer.target_fps == display_config.refresh_rate
    assert frame_buffer.buffer_duration == display_config.buffer_duration
    assert frame_buffer.max_buffer_size == int(
        display_config.refresh_rate * display_config.buffer_duration
    )

    # Test initial state
    assert len(frame_buffer._buffer) == 0
    credits = await frame_buffer.get_credits()
    assert credits == frame_buffer.max_buffer_size  # Start with full credits


@pytest.mark.asyncio
async def test_credit_system(frame_buffer, sample_frame):
    """Test the credit system works correctly."""
    initial_credits = await frame_buffer.get_credits()
    max_credits = frame_buffer.max_buffer_size

    # Should start with full credits
    assert initial_credits == max_credits

    # Consume a credit
    success = await frame_buffer.consume_credit()
    assert success is True

    credits_after_consume = await frame_buffer.get_credits()
    assert credits_after_consume == initial_credits - 1

    # Add credits back
    await frame_buffer.add_credits(2)
    credits_after_add = await frame_buffer.get_credits()
    assert credits_after_add == min(
        initial_credits + 1, max_credits
    )  # Should be capped at max

    # Test consuming when no credits available
    # First, consume all credits
    for _ in range(max_credits):
        await frame_buffer.consume_credit()

    no_credits = await frame_buffer.get_credits()
    assert no_credits == 0

    # Try to consume when none available
    success = await frame_buffer.consume_credit()
    assert success is False


@pytest.mark.asyncio
async def test_frame_buffer_operations(frame_buffer, sample_frame):
    """Test basic frame buffer operations."""
    # Test empty buffer
    frame = await frame_buffer.get_next_frame()
    assert frame is None

    # Add a frame
    success = await frame_buffer.add_frame(sample_frame)
    assert success is True

    # Buffer should have one frame
    status = frame_buffer.get_buffer_status()
    assert status["buffer_size"] == 1
    assert status["buffer_utilization"] > 0

    # Get frame back
    retrieved_frame = await frame_buffer.get_next_frame()
    assert retrieved_frame is not None
    assert retrieved_frame.frame_id == sample_frame.frame_id

    # Buffer should be empty again
    status = frame_buffer.get_buffer_status()
    assert status["buffer_size"] == 0


@pytest.mark.asyncio
async def test_frame_buffer_overflow(frame_buffer, display_config):
    """Test frame buffer handles overflow correctly."""
    max_size = frame_buffer.max_buffer_size

    # Fill buffer to capacity
    # Keep test inputs fixed to a known panel size
    PANEL_W = 28
    PANEL_H = 7
    stride = (PANEL_W + 7) // 8
    for i in range(max_size):
        frame = Frame(
            frame_id=i,
            flags=0,
            width=PANEL_W,
            height=PANEL_H,
            data=b"\x00" * (stride * PANEL_H),
            timestamp=time.time(),
        )
        success = await frame_buffer.add_frame(frame)
        assert success is True

    # Buffer should be full
    status = frame_buffer.get_buffer_status()
    assert status["buffer_size"] == max_size
    assert status["buffer_utilization"] == 1.0

    # Try to add one more frame - should fail
    PANEL_W = 28
    PANEL_H = 7
    stride = (PANEL_W + 7) // 8
    overflow_frame = Frame(
        frame_id=999,
        flags=0,
        width=PANEL_W,
        height=PANEL_H,
        data=b"\x00" * (stride * PANEL_H),
        timestamp=time.time(),
    )
    success = await frame_buffer.add_frame(overflow_frame)
    assert success is False

    # Buffer size should stay the same
    status = frame_buffer.get_buffer_status()
    assert status["buffer_size"] == max_size


@pytest.mark.asyncio
async def test_display_frame_at_rate(frame_buffer, sample_frame):
    """Test frame rate limiting works correctly."""
    # Add a frame to buffer
    await frame_buffer.add_frame(sample_frame)

    # First call should return the frame
    frame1 = await frame_buffer.display_frame_at_rate()
    assert frame1 is not None
    assert frame1.frame_id == sample_frame.frame_id

    # Immediate second call should return None (not enough time passed)
    frame2 = await frame_buffer.display_frame_at_rate()
    assert frame2 is None

    # Wait for frame interval and try again
    await asyncio.sleep(frame_buffer.frame_interval + 0.001)  # Small buffer

    # Should return current frame (buffer fallback since no new frames)
    frame3 = await frame_buffer.display_frame_at_rate()
    assert frame3 is not None
    assert frame3.frame_id == sample_frame.frame_id


@pytest.mark.asyncio
async def test_buffer_health_monitoring(frame_buffer, display_config):
    """Test buffer health monitoring."""
    # Empty buffer should be critical
    health = frame_buffer.get_buffer_health()
    assert health["health"] == "critical"
    assert health["buffer_level"] == 0.0

    # Fill buffer partially
    mid_count = frame_buffer.max_buffer_size // 2
    PANEL_W = 28
    PANEL_H = 7
    stride = (PANEL_W + 7) // 8
    for i in range(mid_count):
        frame = Frame(i, 0, PANEL_W, PANEL_H, b"\x00" * (stride * PANEL_H), time.time())
        await frame_buffer.add_frame(frame)

    health = frame_buffer.get_buffer_health()
    assert health["health"] in ["fair", "good"]  # Should be in middle range
    assert 0.4 < health["buffer_level"] < 0.6


def test_create_frame_for_canvas(display_config):
    """Test creating frame for canvas."""
    # Use a fixed panel size for test data
    PANEL_W = 28
    PANEL_H = 7
    stride = (PANEL_W + 7) // 8
    canvas_data = b"\xff" * (stride * PANEL_H)  # All pixels on using row-stride packing

    frame = create_frame_for_canvas(123, canvas_data, display_config)

    assert frame.frame_id == 123
    assert frame.width == 28
    assert frame.height == 7
    assert frame.data == canvas_data
    assert frame.flags == 0


def test_validate_frame_for_display(display_config):
    """Test frame validation against display configuration."""
    # Valid frame
    PANEL_W = 28
    PANEL_H = 7
    stride = (PANEL_W + 7) // 8
    canvas_data = b"\x00" * (stride * PANEL_H)
    valid_frame = create_frame_for_canvas(1, canvas_data, display_config)
    assert validate_frame_for_display(valid_frame, display_config) is True

    # Invalid dimensions
    invalid_frame = Frame(2, 0, 20, 5, b"\x00" * 13, time.time())
    assert validate_frame_for_display(invalid_frame, display_config) is False

    # Invalid data size
    bad_data_frame = Frame(3, 0, 28, 7, b"\x00" * 10, time.time())  # Too small
    assert validate_frame_for_display(bad_data_frame, display_config) is False

    # Binary parsing moved to Kaitai-based tests; omitted here.


if __name__ == "__main__":
    pytest.main([__file__])
