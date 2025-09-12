"""
Display Protocol Service

Handles protocol selection and configuration decisions based on display characteristics.
Separated from DisplayConfig to follow Single Responsibility Principle.
"""

from typing import TYPE_CHECKING

from .protocol_config import DataBytes, Refresh, get_protocol_config, ProtocolConfig
from .validation import validate_panel_dimensions

if TYPE_CHECKING:
    from .config import DisplayConfig


class DisplayProtocolService:
    """
    Service for making protocol-related decisions based on display configuration.

    Encapsulates the business logic for:
    - Data bytes determination based on panel sizes
    - Refresh mode selection based on panel count
    - Protocol configuration selection
    """

    def __init__(self, display_config: "DisplayConfig"):
        self.display_config = display_config

    def get_data_bytes(self) -> DataBytes:
        """
        Determine the data bytes needed based on panel dimensions.

        Returns:
            DataBytes: The appropriate data bytes enum for the panel configuration

        Raises:
            ValidationError: If panel dimensions don't match supported configurations
        """
        widths = {p.size.w for p in self.display_config.panels}
        heights = {p.size.h for p in self.display_config.panels}

        validate_panel_dimensions(widths, heights)

        if widths == {7}:
            return DataBytes.BYTES_7
        elif widths == {14}:
            return DataBytes.BYTES_14
        elif widths == {28}:
            return DataBytes.BYTES_28
        else:
            # This should never happen after validation, but keeping for safety
            raise ValueError(
                "Unsupported panel widths. Expected all 7, 14, or 28; "
                f"got {sorted(widths)}"
            )

    def get_refresh_mode(self) -> Refresh:
        """
        Determine refresh mode based on panel count.

        Business rule:
        - Multiple panels: use buffered refresh for synchronized updates
        - Single panel: use instant refresh for minimal latency

        Returns:
            Refresh: The appropriate refresh mode
        """
        return (
            Refresh.BUFFER if len(self.display_config.panels) > 1 else Refresh.INSTANT
        )

    def get_protocol_config(self) -> ProtocolConfig:
        """
        Get the complete protocol configuration for this display.

        Combines data_bytes and refresh_mode to get the appropriate protocol.

        Returns:
            ProtocolConfig: Complete protocol configuration

        Raises:
            ValueError: If the combination is not supported
        """
        data_bytes = self.get_data_bytes()
        refresh_mode = self.get_refresh_mode()
        return get_protocol_config(data_bytes, refresh_mode)
