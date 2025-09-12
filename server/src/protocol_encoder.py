"""
Pure Protocol Encoding Logic

This module contains the ProtocolEncoder class, which handles the binary framing
protocol for flip-disc display communication. It's a pure class with no I/O
dependencies that converts panel data to protocol frames.

Frame format: [0x80, address, len_hi, len_lo, <payload bytes...>, 0x8F]
"""

from typing import Dict, Iterable


class ProtocolEncoder:
    """
    Pure protocol encoder for flip-disc display frames.

    This class handles the binary framing protocol without any I/O operations.
    All methods are pure functions that take inputs and return encoded bytes.
    """

    # Protocol constants
    HEADER = 0x80
    EOT = 0x8F

    def encode_panel_frame(self, address: int, payload: bytes) -> bytes:
        """
        Encode a single panel frame with protocol headers.

        Frame format: [0x80, address, len_hi, len_lo, <payload bytes...>, 0x8F]

        Args:
            address: Panel RS-485 address (0-255)
            payload: Panel data bytes

        Returns:
            bytes: Complete protocol frame ready for transmission
        """
        payload_length = len(payload)
        return (
            bytes(
                [
                    self.HEADER,
                    address & 0xFF,
                    (payload_length >> 8) & 0xFF,  # Length high byte
                    payload_length & 0xFF,  # Length low byte
                ]
            )
            + payload
            + bytes([self.EOT])
        )

    def encode_many(self, panel_payloads: Dict[int, bytes]) -> Iterable[bytes]:
        """
        Encode multiple panel frames.

        Args:
            panel_payloads: Dict mapping panel address to payload bytes

        Yields:
            bytes: Protocol frames ready for transmission
        """
        for address, payload in panel_payloads.items():
            yield self.encode_panel_frame(address, payload)

    def encode_flush(self, flush_command: bytes) -> bytes:
        """
        Encode a flush/refresh command frame.

        Args:
            flush_command: Raw flush command bytes

        Returns:
            bytes: Encoded flush frame (may be pass-through if already framed)
        """
        # If flush command already includes framing, pass through
        # Otherwise, could wrap it similarly to encode_panel_frame
        return flush_command
