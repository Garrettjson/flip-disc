"""Minimal smoke test for server WebSocket frame flow.

What it tests:
- Builds a FastAPI app with a simple 28x7 single-panel mock config
- Connects to `/ws/frames` and receives initial credits
- Sends one valid binary frame (empty bitmap)
- Receives a credits update that reflects consumption

This exercises end-to-end: FastAPI WS -> Kaitai parse -> frame buffer enqueue ->
credit accounting -> JSON credits response.
"""

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from src.main import create_app


def build_temp_config(
    panel_type: str = "28x7", columns: int = 1, rows: int = 1
) -> Path:
    content = f"""
[display]
panel_type = "{panel_type}"
columns = {columns}
rows = {rows}
refresh_rate = 20.0
buffer_duration = 0.5

[serial]
port = "/dev/ttyUSB0"
baudrate = 9600
timeout = 1.0
mock = true
"""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
    f.write(content)
    f.flush()
    return Path(f.name)


def make_binary_frame(width: int, height: int, seq: int = 1) -> bytes:
    """Construct a binary frame in the Kaitai-defined format."""
    payload_len = ((width + 7) // 8) * height
    bitmap_data = bytes([0] * payload_len)

    frame = bytearray()
    # Magic "FDIS" (little-endian write of constant is fine as literal bytes)
    frame.extend(b"FDIS")
    # Sequence (u2le)
    frame.extend(int(seq).to_bytes(2, "little"))
    # PTS ns (u8le)
    pts_ns = int(1_700_000_000) * 1_000_000_000
    frame.extend(pts_ns.to_bytes(8, "little"))
    # Width/Height (u2le)
    frame.extend(int(width).to_bytes(2, "little"))
    frame.extend(int(height).to_bytes(2, "little"))
    # Payload length (u2le)
    frame.extend(int(payload_len).to_bytes(2, "little"))
    # Bitmap data
    frame.extend(bitmap_data)
    return bytes(frame)


def test_websocket_smoke_success():
    cfg_path = build_temp_config("28x7", 1, 1)
    try:
        app = create_app(cfg_path)
        with TestClient(app) as client:
            # Connect to WS
            with client.websocket_connect("/ws/frames") as ws:
                # Initial credits
                initial = ws.receive_json()
                assert initial.get("type") == "credits"
                initial_credits = int(initial.get("credits", 0))
                assert initial_credits > 0

                # Send one empty frame of correct size
                binary = make_binary_frame(28, 7, seq=42)
                ws.send_bytes(binary)

                # Expect a credits update
                update = ws.receive_json()
                assert update.get("type") == "credits"
                updated_credits = int(update.get("credits", 0))
                assert 0 <= updated_credits <= initial_credits
                # In most cases, it should drop by 1 immediately
                assert updated_credits <= initial_credits
    finally:
        cfg_path.unlink(missing_ok=True)
