"""
Pure Protocol Encoding Logic

This module contains the ProtocolEncoder class, which handles the binary framing
protocol for flip-disc display communication. It's a pure class with no I/O
dependencies that converts panel data to protocol frames.

Frame format: [0x80, address, len_hi, len_lo, <payload bytes...>, 0x8F]
"""

from typing import Dict, Iterable
from .protocol_config import ProtocolConfig, FRAME_START, FRAME_END, FLUSH_COMMAND


class ProtocolEncoder:
    """
    Pure protocol encoder for flip-disc display frames.

    This class handles the binary framing protocol without any I/O operations.
    All methods are pure functions that take inputs and return encoded bytes.
    """

    # Protocol constants
    HEADER = FRAME_START
    EOT = FRAME_END

    def encode_panel_frame(
        self, address: int, payload: bytes, protocol: ProtocolConfig
    ) -> bytes:
        """
        Encode a single panel frame with protocol headers.

        Frame format (manufacturer spec):
        [0x80, command, address, <payload bytes...>, 0x8F]

        Args:
            address: Panel RS-485 address (0-255)
            payload: Panel data bytes
            protocol: Protocol configuration (provides command byte)

        Returns:
            bytes: Complete protocol frame ready for transmission
        """
        return (
            bytes([self.HEADER, protocol.command_byte, address & 0xFF])
            + payload
            + bytes([self.EOT])
        )

    def encode_many(
        self, panel_payloads: Dict[int, bytes], protocol: ProtocolConfig
    ) -> Iterable[bytes]:
        """
        Encode multiple panel frames.

        Args:
            panel_payloads: Dict mapping panel address to payload bytes
            protocol: Protocol configuration

        Yields:
            bytes: Protocol frames ready for transmission
        """
        for address, payload in panel_payloads.items():
            yield self.encode_panel_frame(address, payload, protocol)

    def encode_flush(self) -> bytes:
        """
        Encode a flush/refresh-all command frame.

        Returns:
            bytes: Encoded flush frame ([0x80, 0x82, 0x8F])
        """
        return bytes([self.HEADER, FLUSH_COMMAND, self.EOT])
