"""Graphics processing modules for flip-disc displays."""

from .dither import error_diffusion_floyd_steinberg, ordered_bayer, simple_threshold

__all__ = [
    "error_diffusion_floyd_steinberg",
    "ordered_bayer",
    "simple_threshold",
]
