from __future__ import annotations

import struct
from dataclasses import dataclass


HEADER_SIZE = 16


@dataclass
class Header:
    magic: bytes
    version: int
    flags: int
    width: int
    height: int
    seq: int
    frame_duration_ms: int
    reserved: int


def parse_header(data: bytes) -> tuple[Header, int]:
    if len(data) < HEADER_SIZE:
        raise ValueError("short header")
    # > big-endian; 2s B B H H I H H
    magic, version, flags, width, height, seq, dur, res = struct.unpack(
        ">2sBBHHIHH", data[:HEADER_SIZE]
    )
    if magic != b"RB" or version != 1:
        raise ValueError("bad magic/version")
    return Header(magic, version, flags, width, height, seq, dur, res), HEADER_SIZE

