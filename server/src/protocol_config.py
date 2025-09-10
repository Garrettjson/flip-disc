"""
Flipdots display protocol configuration.

Based on manufacturer documentation from flipdots_protocols.md.
Frame format: 0x80 Command Address Data 0x8F
"""

from enum import Enum
from typing import NamedTuple


class DataBytes(Enum):
    """Number of data bytes for different panel configurations."""
    
    BYTES_7 = 7    # 7x7 panels
    BYTES_14 = 14  # 14x7 panels  
    BYTES_28 = 28  # 28x7 panels

    def __str__(self) -> str:
        return f"{self.value} bytes"


class Refresh(Enum):
    """Panel refresh behavior."""
    
    INSTANT = "instant"  # Show data as soon as received (Refresh=YES)
    BUFFER = "buffer"    # Store data, show on flush command (Refresh=NO)

    def __str__(self) -> str:
        return self.value


class ProtocolConfig(NamedTuple):
    """Protocol configuration for a data size and refresh mode."""
    
    command_byte: int
    data_bytes: int
    supports_buffered: bool
    description: str


# Protocol mapping based on manufacturer documentation
# Frame: 0x80 Command Address Data 0x8F
PROTOCOL_MAP = {
    # 7 bytes (7x7 panels - only instant refresh supported)
    (DataBytes.BYTES_7, Refresh.INSTANT): ProtocolConfig(
        command_byte=0x87,
        data_bytes=7,
        supports_buffered=False,
        description="7x7 instant refresh"
    ),
    
    # 14 bytes (14x7 panels - both instant and buffered supported)
    (DataBytes.BYTES_14, Refresh.INSTANT): ProtocolConfig(
        command_byte=0x92,
        data_bytes=14,
        supports_buffered=True,
        description="14x7 instant refresh"
    ),
    (DataBytes.BYTES_14, Refresh.BUFFER): ProtocolConfig(
        command_byte=0x93,
        data_bytes=14,
        supports_buffered=True,
        description="14x7 buffered refresh"
    ),
    
    # 28 bytes (28x7 panels - both instant and buffered supported)
    (DataBytes.BYTES_28, Refresh.INSTANT): ProtocolConfig(
        command_byte=0x83,
        data_bytes=28,
        supports_buffered=True,
        description="28x7 instant refresh"
    ),
    (DataBytes.BYTES_28, Refresh.BUFFER): ProtocolConfig(
        command_byte=0x84,
        data_bytes=28,
        supports_buffered=True,
        description="28x7 buffered refresh"
    ),
}


# Special protocol commands
FRAME_START = 0x80      # Frame start byte
FRAME_END = 0x8F        # Frame end byte
FLUSH_COMMAND = 0x82    # Refresh all buffered displays (0 data bytes)
BROADCAST_ADDRESS = 0xFF  # Address for all devices


def get_protocol_config(data_bytes: DataBytes, refresh: Refresh) -> ProtocolConfig:
    """Get protocol configuration for given data size and refresh mode.
    
    Args:
        data_bytes: The number of data bytes (panel payload size)
        refresh: Instant or buffered refresh
        
    Returns:
        ProtocolConfig with command byte and metadata
        
    Raises:
        ValueError: If the combination is not supported
    """
    config = PROTOCOL_MAP.get((data_bytes, refresh))
    if not config:
        raise ValueError(
            f"Unsupported configuration: {data_bytes} with {refresh} refresh"
        )
    return config


def data_bytes_from_panel_size(width: int, height: int) -> DataBytes:
    """Get DataBytes enum from panel dimensions.
    
    Args:
        width: Panel width in dots
        height: Panel height in dots
        
    Returns:
        DataBytes enum value
        
    Raises:
        ValueError: If dimensions don't match a supported panel size
    """
    # Panel data bytes = width (one byte per column strip)
    if width == 7 and height == 7:
        return DataBytes.BYTES_7
    elif width == 14 and height == 7:
        return DataBytes.BYTES_14
    elif width == 28 and height == 7:
        return DataBytes.BYTES_28
    else:
        raise ValueError(
            f"Unsupported panel size: {width}x{height}. "
            f"Supported sizes: 7x7, 14x7, 28x7"
        )


def supports_buffered_refresh(data_bytes: DataBytes) -> bool:
    """Check if a data size supports buffered refresh mode.
    
    Args:
        data_bytes: The data size to check
        
    Returns:
        True if buffered refresh is supported, False otherwise
    """
    # Check if there's a buffered configuration for this data size
    return (data_bytes, Refresh.BUFFER) in PROTOCOL_MAP