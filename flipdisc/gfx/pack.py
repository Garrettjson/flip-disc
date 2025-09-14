"""Frame packing utilities for flip-disc displays."""

import numpy as np

from ..exceptions import FrameError


def pack_msb_first(binary_image: np.ndarray) -> bytes:
    """
    Pack binary image into bytes with MSB-first bit ordering.

    This is the main packing function used by the animation pipeline.
    Each row is packed independently with MSB-first ordering within each byte.

    Args:
        binary_image: 2D boolean array representing the binary image

    Returns:
        Packed bytes ready for transmission

    Raises:
        FrameError: If input format is invalid
    """
    if not isinstance(binary_image, np.ndarray):
        raise FrameError(f"Image must be numpy array, got {type(binary_image)}")
    if binary_image.ndim != 2:
        raise FrameError(f"Image must be 2D, got {binary_image.ndim}D")
    if binary_image.dtype != bool:
        raise FrameError(f"Image must be boolean, got {binary_image.dtype}")

    _height, width = binary_image.shape

    # Calculate bytes per row (round up to byte boundary)
    bytes_per_row = (width + 7) // 8

    # Pack each row independently
    packed_rows = []
    for row in binary_image:
        # Pad row to byte boundary
        padded_width = bytes_per_row * 8
        padded_row = np.zeros(padded_width, dtype=bool)
        padded_row[:width] = row

        # Pack to bytes using numpy (MSB first = 'big' bit order)
        packed_row = np.packbits(padded_row, bitorder="big")
        packed_rows.append(packed_row.tobytes())

    return b"".join(packed_rows)


def pack_lsb_first(binary_image: np.ndarray) -> bytes:
    """
    Pack binary image into bytes with LSB-first bit ordering.

    Alternative packing format for hardware that expects LSB-first.

    Args:
        binary_image: 2D boolean array representing the binary image

    Returns:
        Packed bytes with LSB-first ordering
    """
    if not isinstance(binary_image, np.ndarray):
        raise FrameError(f"Image must be numpy array, got {type(binary_image)}")
    if binary_image.ndim != 2:
        raise FrameError(f"Image must be 2D, got {binary_image.ndim}D")
    if binary_image.dtype != bool:
        raise FrameError(f"Image must be boolean, got {binary_image.dtype}")

    _height, width = binary_image.shape
    bytes_per_row = (width + 7) // 8

    packed_rows = []
    for row in binary_image:
        padded_width = bytes_per_row * 8
        padded_row = np.zeros(padded_width, dtype=bool)
        padded_row[:width] = row

        # Pack with LSB-first ordering
        packed_row = np.packbits(padded_row, bitorder="little")
        packed_rows.append(packed_row.tobytes())

    return b"".join(packed_rows)


def unpack_frame(
    frame_bytes: bytes, width: int, height: int, bit_order: str = "big"
) -> np.ndarray:
    """
    Unpack frame bytes back into binary image.

    Useful for debugging and testing the packing pipeline.

    Args:
        frame_bytes: Packed frame data
        width: Image width in pixels
        height: Image height in pixels
        bit_order: 'big' for MSB-first, 'little' for LSB-first

    Returns:
        2D boolean array representing the unpacked image
    """
    if not isinstance(frame_bytes, bytes):
        raise FrameError(f"Frame data must be bytes, got {type(frame_bytes)}")
    if width <= 0 or height <= 0:
        raise FrameError(f"Dimensions must be positive: {width}x{height}")
    if bit_order not in ["big", "little"]:
        raise FrameError(f"Bit order must be 'big' or 'little', got '{bit_order}'")

    bytes_per_row = (width + 7) // 8
    expected_size = height * bytes_per_row

    if len(frame_bytes) != expected_size:
        raise FrameError(
            f"Frame size mismatch: expected {expected_size} bytes, got {len(frame_bytes)}"
        )

    # Convert to numpy array and unpack
    frame_array = np.frombuffer(frame_bytes, dtype=np.uint8)
    frame_array = frame_array.reshape((height, bytes_per_row))

    # Unpack bits
    unpacked = np.unpackbits(frame_array, axis=1, bitorder=bit_order)

    # Trim to actual width
    return unpacked[:, :width].astype(bool)


def validate_frame_size(frame_bytes: bytes, width: int, height: int) -> bool:
    """
    Validate that frame bytes match expected dimensions.

    Args:
        frame_bytes: Packed frame data
        width: Expected width in pixels
        height: Expected height in pixels

    Returns:
        True if size matches, False otherwise
    """
    if not isinstance(frame_bytes, bytes):
        return False

    bytes_per_row = (width + 7) // 8
    expected_size = height * bytes_per_row

    return len(frame_bytes) == expected_size
