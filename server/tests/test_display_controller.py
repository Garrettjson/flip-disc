"""Tests for DisplayController and frame mapping."""

import pytest
import numpy as np

from src.config import DisplayConfig, PanelConfig, SerialConfig, Point, Size
from src.display_controller import DisplayController, PanelFrameError, CanvasFrameError
from src.frame_mapper import FrameMapper


@pytest.fixture
def single_panel_config() -> DisplayConfig:
    panel = PanelConfig(
        id="main",
        origin=Point(0, 0),
        size=Size(28, 7),
        address=0,
    )
    cfg = DisplayConfig(
        canvas_size=Size(28, 7),
        panels=[panel],
        serial=SerialConfig(port="/dev/ttyUSB0", baudrate=9600, timeout=1.0, mock=True),
        refresh_rate=20.0,
        buffer_duration=0.5,
    )
    # Validate relationships
    cfg.validate_within_canvas()
    _ = cfg.protocol_config
    return cfg


@pytest.mark.asyncio
async def test_connect_disconnect(single_panel_config: DisplayConfig):
    dc = DisplayController(single_panel_config)
    assert not dc.is_connected()

    await dc.connect()
    assert dc.is_connected()

    await dc.disconnect()
    assert not dc.is_connected()


@pytest.mark.asyncio
async def test_send_panel_frame_success_and_errors(single_panel_config: DisplayConfig):
    dc = DisplayController(single_panel_config)
    await dc.connect()

    # Valid frame for 28x7 panel (H, W)
    frame = np.zeros((7, 28), dtype=bool)
    frame[0, :] = True
    await dc.send_panel_frame(0, frame)

    # Invalid address
    with pytest.raises(PanelFrameError):
        await dc.send_panel_frame(99, frame)

    # Wrong shape
    wrong = np.zeros((5, 20), dtype=bool)
    with pytest.raises(PanelFrameError):
        await dc.send_panel_frame(0, wrong)


@pytest.mark.asyncio
async def test_send_canvas_frame(single_panel_config: DisplayConfig):
    dc = DisplayController(single_panel_config)
    await dc.connect()

    # Create a test pattern via FrameMapper
    fm = FrameMapper()
    canvas_bits = fm.create_test_pattern(28, 7, "checkerboard")

    await dc.send_canvas_frame(canvas_bits)

    # Bad canvas size should raise CanvasFrameError
    with pytest.raises(CanvasFrameError):
        await dc.send_canvas_frame(b"\x00" * 4)


@pytest.mark.asyncio
async def test_get_display_stats(single_panel_config: DisplayConfig):
    dc = DisplayController(single_panel_config)
    await dc.connect()
    stats = dc.get_display_stats()
    assert stats["panel_count"] == 1
    assert stats["connected"] is True
    assert stats["canvas_size"] == "28x7"
