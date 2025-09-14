"""Protocol constants and enums for Flipdots panels.

Centralizes magic numbers from the protocol to improve readability and safety.
"""

from enum import IntEnum


# Frame delimiters
START_BYTE = 0x80
END_BYTE = 0x8F


# Special addresses
BROADCAST_ADDRESS = 0xFF


# Panel geometry constants
PANEL_HEIGHT = 7  # All supported panels are 7 pixels tall


class Command(IntEnum):
    """Protocol command bytes.

    Naming convention: W{width}_{mode}
    where mode is REFRESH (immediate display) or BUFFERED (store then refresh).
    """

    # Global
    FLUSH = 0x82

    # 28x7
    W28_REFRESH = 0x83
    W28_BUFFERED = 0x84

    # 7x7 (buffered not supported per spec)
    W7_REFRESH = 0x87

    # 14x7
    W14_REFRESH = 0x92
    W14_BUFFERED = 0x93

