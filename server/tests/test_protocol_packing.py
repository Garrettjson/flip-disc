"""Verify protocol payload is column-wise with LSB=top (manufacturer spec)."""

import pytest
import numpy as np

from src.config import DisplayConfig, PanelConfig, SerialConfig, Point, Size
from src.display_controller import DisplayController


@pytest.mark.asyncio
async def test_column_wise_packing_payload():
    # Single 28x7 panel
    cfg = DisplayConfig(
        canvas_size=Size(28, 7),
        panels=[PanelConfig("p", Point(0, 0), Size(28, 7), address=0)],
        serial=SerialConfig(mock=True),
    )
    cfg.validate_within_canvas()
    _ = cfg.protocol_config

    dc = DisplayController(cfg)
    await dc.connect()

    captured: list[bytes] = []

    # Monkeypatch write_frames to capture encoded frames
    async def capture_frames(frames):
        for f in frames:
            captured.append(bytes(f))

    dc.serial_port.write_frames = capture_frames  # type: ignore[assignment]

    # Build a canvas with distinct column patterns:
    # col0: top pixel on only -> payload byte bit0=1 -> 0b00000001
    # col1: middle row (row 3) on -> bit3=1 -> 0b00001000
    # col2: bottom (row 6) on -> bit6=1 -> 0b01000000
    h, w = 7, 28
    canvas = np.zeros((h, w), dtype=bool)
    canvas[0, 0] = True
    canvas[3, 1] = True
    canvas[6, 2] = True

    # Pack canvas row-wise to send to server (server unpacks internally)
    canvas_bits = np.packbits(canvas, axis=1, bitorder="big").tobytes()

    await dc.send_canvas_frame(canvas_bits)

    # One frame for single panel (no flush)
    assert len(captured) == 1
    frame = captured[0]

    # Frame format: [0x80, command, address, payload..., 0x8F]
    assert frame[0] == 0x80 and frame[-1] == 0x8F
    payload = frame[3:-1]

    # Expected first three payload bytes
    assert payload[0] == 0b00000001
    assert payload[1] == 0b00001000
    assert payload[2] == 0b01000000
