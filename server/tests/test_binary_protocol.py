#!/usr/bin/env python3
"""Tests for flip disc binary protocol via Kaitai parser."""

from gen.py.flipdisc_frame import FlipdiscFrame


def create_test_frame(width=28, height=7, seq=1):
    """Create a test frame with checkerboard pattern"""
    # Calculate payload size
    payload_len = ((width + 7) // 8) * height

    # Create checkerboard pattern
    bitmap_data = bytearray(payload_len)
    for y in range(height):
        row_start_byte = y * ((width + 7) // 8)
        for x in range(width):
            bit_pos = 7 - (x % 8)
            byte_idx = row_start_byte + x // 8
            if (x + y) % 2 == 0:  # Checkerboard pattern
                bitmap_data[byte_idx] |= 1 << bit_pos

    # Build complete frame according to our binary protocol
    frame_data = bytearray()

    # Magic "FDIS" (0x46444953)
    frame_data.extend([0x46, 0x44, 0x49, 0x53])

    # Sequence number (2 bytes, little-endian)
    frame_data.extend(seq.to_bytes(2, "little"))

    # Timestamp (4 bytes, little-endian)
    timestamp = 1694649600  # Fixed timestamp for testing
    frame_data.extend(timestamp.to_bytes(4, "little"))

    # Width (2 bytes, little-endian)
    frame_data.extend(width.to_bytes(2, "little"))

    # Height (2 bytes, little-endian)
    frame_data.extend(height.to_bytes(2, "little"))

    # Payload length (2 bytes, little-endian)
    frame_data.extend(payload_len.to_bytes(2, "little"))

    # Bitmap data
    frame_data.extend(bitmap_data)

    return bytes(frame_data)


def test_valid_frame():
    """Parsing a valid frame succeeds and validates sizes."""
    frame_data = create_test_frame(28, 7, 42)
    parsed = FlipdiscFrame.from_bytes(frame_data)
    assert parsed.magic == b"FDIS"
    assert parsed.width == 28 and parsed.height == 7
    assert parsed.payload_len == parsed.expected_payload_len
    assert len(parsed.bitmap_data) == parsed.payload_len


def test_invalid_magic():
    """Invalid magic number raises validation error."""
    frame_data = bytearray(create_test_frame(28, 7, 1))
    frame_data[0:4] = b"BADD"
    try:
        FlipdiscFrame.from_bytes(bytes(frame_data))
        assert False, "Expected validation error for invalid magic"
    except Exception:
        assert True


def test_payload_mismatch():
    """Mismatched payload length raises validation error."""
    frame_data = bytearray(create_test_frame(28, 7, 1))
    # Corrupt payload_len field (bytes 12..13 for width/height, 14..15 payload_len)
    frame_data[14] = 10
    frame_data[15] = 0
    try:
        FlipdiscFrame.from_bytes(bytes(frame_data))
        assert False, "Expected validation error for payload mismatch"
    except Exception:
        assert True


if __name__ == "__main__":
    # Allow running under pytest -q; direct execution is optional
    import pytest

    raise SystemExit(pytest.main([__file__]))
