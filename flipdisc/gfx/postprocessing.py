"""Post-processing functions for animation frames."""

from __future__ import annotations

import numpy as np
from scipy import ndimage
from skimage import filters


def binarize(frame: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    return (frame > threshold).astype(np.bool_)


def dither(frame: np.ndarray) -> np.ndarray:
    return (filters.threshold_local(frame, 3) < frame).astype(np.bool_)


def blur(frame: np.ndarray, sigma: float = 1.0) -> np.ndarray:
    return ndimage.gaussian_filter(frame, sigma=sigma)


def sharpen(frame: np.ndarray, strength: float = 1.0) -> np.ndarray:
    kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]]) * strength / 9
    return ndimage.convolve(frame, kernel)


def threshold(frame: np.ndarray, low: float = 0.3, high: float = 0.7) -> np.ndarray:
    result = frame.copy()
    result[frame < low] = 0.0
    result[frame > high] = 1.0
    return result


PROCESSING_FUNCTIONS = {
    "binarize": binarize,
    "dither": dither,
    "blur": blur,
    "sharpen": sharpen,
    "threshold": threshold,
}


def apply_processing_pipeline(
    frame: np.ndarray, steps: tuple[str, ...] | None
) -> np.ndarray:
    if steps is None:
        return frame

    processed_frame = frame
    for step_name in steps:
        if step_name not in PROCESSING_FUNCTIONS:
            raise ValueError(f"Unknown processing step: {step_name}")
        processed_frame = PROCESSING_FUNCTIONS[step_name](processed_frame)

    return processed_frame
