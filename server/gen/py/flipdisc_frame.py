# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import KaitaiStruct, KaitaiStream, BytesIO


if getattr(kaitaistruct, "API_VERSION", (0, 9)) < (0, 11):
    raise Exception(
        "Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s"
        % (kaitaistruct.__version__)
    )


class FlipdiscFrame(KaitaiStruct):
    """Binary protocol for flip disc display frames.

    Each frame contains:
    - Fixed 16-byte header with magic, sequence, timestamp, dimensions
    - Variable-length bitmap payload (1 bit per pixel, packed)

    The payload length is validated to match ceil(width/8) * height.
    """

    def __init__(self, _io, _parent=None, _root=None):
        super(FlipdiscFrame, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self
        self._read()

    def _read(self):
        self.magic = self._io.read_bytes(4)
        if not self.magic == b"\x46\x44\x49\x53":
            raise kaitaistruct.ValidationNotEqualError(
                b"\x46\x44\x49\x53", self.magic, self._io, "/seq/0"
            )
        self.seq = self._io.read_u2le()
        self.timestamp = self._io.read_u4le()
        self.width = self._io.read_u2le()
        if not self.width >= 1:
            raise kaitaistruct.ValidationLessThanError(
                1, self.width, self._io, "/seq/3"
            )
        if not self.width <= 1024:
            raise kaitaistruct.ValidationGreaterThanError(
                1024, self.width, self._io, "/seq/3"
            )
        self.height = self._io.read_u2le()
        if not self.height >= 1:
            raise kaitaistruct.ValidationLessThanError(
                1, self.height, self._io, "/seq/4"
            )
        if not self.height <= 1024:
            raise kaitaistruct.ValidationGreaterThanError(
                1024, self.height, self._io, "/seq/4"
            )
        self.payload_len = self._io.read_u2le()
        _ = self.payload_len
        if not self.payload_len == self.expected_payload_len:
            raise kaitaistruct.ValidationExprError(self.payload_len, self._io, "/seq/5")
        self.bitmap_data = self._io.read_bytes(self.payload_len)

    def _fetch_instances(self):
        pass

    @property
    def bytes_per_row(self):
        """Number of bytes needed per row of pixels."""
        if hasattr(self, "_m_bytes_per_row"):
            return self._m_bytes_per_row

        self._m_bytes_per_row = (self.width + 7) // 8
        return getattr(self, "_m_bytes_per_row", None)

    @property
    def expected_payload_len(self):
        """Expected payload length based on width and height."""
        if hasattr(self, "_m_expected_payload_len"):
            return self._m_expected_payload_len

        self._m_expected_payload_len = ((self.width + 7) // 8) * self.height
        return getattr(self, "_m_expected_payload_len", None)

    @property
    def total_pixels(self):
        """Total number of pixels in the frame."""
        if hasattr(self, "_m_total_pixels"):
            return self._m_total_pixels

        self._m_total_pixels = self.width * self.height
        return getattr(self, "_m_total_pixels", None)
