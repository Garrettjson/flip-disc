"""
Cross-cutting validation logic for flip-disc display system.

This module provides validation functions for global/cross-object rules that
span multiple components. Type-local invariants should remain in their
respective dataclass __post_init__ methods.

Cross-cutting rules validated here:
- Panel dimension consistency across all panels
- Panel address uniqueness
- Panel overlap detection  
- Canvas bounds checking for all panels
- Canvas data size validation
- Display configuration consistency
"""

from typing import Set, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import DisplayConfig


class ValidationError(ValueError):
    """Base exception for validation errors."""
    pass


class PanelValidationError(ValidationError):
    """Raised when panel configuration is invalid."""
    pass


class CanvasValidationError(ValidationError):
    """Raised when canvas configuration is invalid."""
    pass


def validate_panel_dimensions(widths: Set[int], heights: Set[int]) -> None:
    """
    Validate panel dimensions against supported configurations.
    
    Cross-cutting rule: All panels must share supported dimensions.
    
    Args:
        widths: Set of panel widths
        heights: Set of panel heights
        
    Raises:
        PanelValidationError: If dimensions don't match supported configurations
    """
    if heights != {7}:
        raise PanelValidationError(f"Protocol expects panel height 7, got {sorted(heights)}")
        
    if not (widths <= {7, 14, 28}):
        raise PanelValidationError(
            "Unsupported panel widths. Expected all 7, 14, or 28; "
            f"got {sorted(widths)}"
        )


def validate_canvas_data_size(data_length: int, canvas_w: int, canvas_h: int) -> None:
    """
    Validate that canvas data size matches expected dimensions.
    
    Cross-cutting rule: Canvas data must match computed size requirements.
    
    Args:
        data_length: Length of canvas data in bytes
        canvas_w: Canvas width in pixels
        canvas_h: Canvas height in pixels
        
    Raises:
        CanvasValidationError: If data size doesn't match expected size
    """
    stride = (canvas_w + 7) // 8  # Bytes per row (rounded up to byte boundary)
    expected_bytes = canvas_h * stride
    
    if data_length != expected_bytes:
        raise CanvasValidationError(
            f"Canvas data size {data_length} doesn't match expected {expected_bytes} "
            f"for {canvas_w}x{canvas_h} canvas"
        )


def validate_canvas_region_bounds(x0: int, y0: int, w: int, h: int, 
                                 canvas_w: int, canvas_h: int, 
                                 panel_id: str = "unknown", 
                                 panel_address: int = -1) -> None:
    """
    Validate that a rectangular region is within canvas bounds.
    
    Cross-cutting rule: Panel regions must fit within canvas.
    
    Args:
        x0, y0: Origin coordinates
        w, h: Region dimensions
        canvas_w, canvas_h: Canvas dimensions
        panel_id: Panel ID for error messages
        panel_address: Panel address for error messages
        
    Raises:
        CanvasValidationError: If region is out of bounds
    """
    if not (0 <= x0 < canvas_w and 0 <= y0 < canvas_h and x0 + w <= canvas_w and y0 + h <= canvas_h):
        raise CanvasValidationError(
            f"Panel '{panel_id}' (addr={panel_address}) region out of bounds: "
            f"origin=({x0},{y0}) size=({w}x{h}) within canvas=({canvas_w}x{canvas_h})"
        )


def validate_display_config(config: "DisplayConfig") -> None:
    """
    Validate cross-cutting rules for a complete display configuration.
    
    This function checks global consistency rules that span multiple panels
    or the entire display configuration.
    
    Args:
        config: Display configuration to validate
        
    Raises:
        ValidationError: If any cross-cutting validation rules fail
    """
    # Validate refresh rate and buffer duration (global config rules)
    if config.refresh_rate <= 0:
        raise ValidationError("refresh_rate must be > 0")
    if config.buffer_duration < 0:
        raise ValidationError("buffer_duration must be >= 0")
    
    if not config.panels:
        raise ValidationError("Display must have at least one panel")
    
    # Check panel dimension consistency (cross-panel rule)
    widths = {p.size.w for p in config.panels}
    heights = {p.size.h for p in config.panels}
    validate_panel_dimensions(widths, heights)
    
    # Check address uniqueness (cross-panel rule)
    addresses = [p.address for p in config.panels]
    if len(addresses) != len(set(addresses)):
        duplicates = [addr for addr in set(addresses) if addresses.count(addr) > 1]
        raise PanelValidationError(f"Duplicate panel addresses: {duplicates}")
    
    # Check canvas bounds for all panels (cross-panel rule)
    canvas_w, canvas_h = config.canvas_size.w, config.canvas_size.h
    for panel in config.panels:
        x0, y0 = panel.origin.x, panel.origin.y
        w, h = panel.size.w, panel.size.h
        
        if x0 + w > canvas_w or y0 + h > canvas_h:
            raise CanvasValidationError(
                f"Panel '{panel.id}' (addr={panel.address}) out of canvas bounds: "
                f"origin=({x0},{y0}) size=({w}x{h}) in canvas=({canvas_w}x{canvas_h})"
            )
    
    # Optional: Check for panel overlaps (cross-panel rule)
    _check_panel_overlaps(config.panels)


def _check_panel_overlaps(panels) -> None:
    """
    Check if any panels overlap with each other.
    
    Args:
        panels: List of panel configurations
        
    Raises:
        PanelValidationError: If any panels overlap
    """
    for i, panel1 in enumerate(panels):
        for panel2 in panels[i+1:]:
            if _panels_overlap(panel1, panel2):
                raise PanelValidationError(
                    f"Panels '{panel1.id}' and '{panel2.id}' overlap"
                )


def _panels_overlap(panel1, panel2) -> bool:
    """Check if two panels overlap."""
    # Panel 1 bounds
    x1, y1 = panel1.origin.x, panel1.origin.y
    x1_end, y1_end = x1 + panel1.size.w, y1 + panel1.size.h
    
    # Panel 2 bounds  
    x2, y2 = panel2.origin.x, panel2.origin.y
    x2_end, y2_end = x2 + panel2.size.w, y2 + panel2.size.h
    
    # No overlap if one panel is completely to the left/right/above/below the other
    return not (x1_end <= x2 or x2_end <= x1 or y1_end <= y2 or y2_end <= y1)