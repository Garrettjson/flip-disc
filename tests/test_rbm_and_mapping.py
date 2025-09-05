import struct

import server.rbm as rbm
from server.config import load_config
from server.mapping import update_panels


def make_rbm(width: int, height: int, seq: int = 1, dur_ms: int = 33) -> bytes:
    stride = (width + 7) // 8
    payload = bytes(height * stride)
    header = struct.pack(
        ">2sBBHHIHH",
        b"RB", 1, 0, width, height, seq, dur_ms, 0,
    )
    return header + payload


def test_rbm_header_parse():
    buf = make_rbm(28, 14, seq=123, dur_ms=40)
    hdr, off = rbm.parse_header(buf)
    assert off == rbm.HEADER_SIZE
    assert hdr.magic == b"RB"
    assert hdr.version == 1
    assert hdr.width == 28 and hdr.height == 14
    assert hdr.seq == 123 and hdr.frame_duration_ms == 40


def test_mapping_two_panels_top_pixel(tmp_path):
    cfg = load_config("config/display.yaml")
    w, h = cfg.canvas.width, cfg.canvas.height
    stride = (w + 7) // 8
    # set a single pixel at (x=0,y=0)
    frame = bytearray(h * stride)
    frame[0] = 0b1000_0000
    panels = update_panels(bytes(frame), w, h, cfg)
    assert "top" in panels and "bottom" in panels
    top = panels["top"]
    bottom = panels["bottom"]
    # first bit of first byte set in top panel
    assert top[0] & 0b1000_0000 != 0
    # bottom panel should be empty
    assert all(b == 0 for b in bottom)

