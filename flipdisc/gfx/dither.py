"""Dithering algorithms for flip-disc displays."""

import numpy as np

from ..core.exceptions import FrameError


def ordered_bayer(gray_image: np.ndarray, threshold_matrix_size: int = 2) -> np.ndarray:
    """
    Apply ordered Bayer dithering to convert grayscale to binary.

    Args:
        gray_image: Grayscale image as float array (0.0 to 1.0)
        threshold_matrix_size: Size of Bayer matrix (2, 4, or 8)

    Returns:
        Binary image as boolean array

    Raises:
        FrameError: If input format is invalid
    """
    if not isinstance(gray_image, np.ndarray):
        raise FrameError(f"Image must be numpy array, got {type(gray_image)}")
    if gray_image.ndim != 2:
        raise FrameError(f"Image must be 2D, got {gray_image.ndim}D")
    if gray_image.dtype not in [np.float32, np.float64]:
        raise FrameError(f"Image must be float, got {gray_image.dtype}")
    if gray_image.min() < 0 or gray_image.max() > 1:
        raise FrameError(
            f"Image values must be 0-1, got range {gray_image.min():.3f}-{gray_image.max():.3f}"
        )

    height, width = gray_image.shape

    # Bayer threshold matrices
    if threshold_matrix_size == 2:
        bayer = np.array([[0, 2], [3, 1]], dtype=np.float32) / 4.0
    elif threshold_matrix_size == 4:
        bayer = (
            np.array(
                [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]],
                dtype=np.float32,
            )
            / 16.0
        )
    elif threshold_matrix_size == 8:
        # 8x8 Bayer matrix for fine dithering
        bayer = (
            np.array(
                [
                    [0, 32, 8, 40, 2, 34, 10, 42],
                    [48, 16, 56, 24, 50, 18, 58, 26],
                    [12, 44, 4, 36, 14, 46, 6, 38],
                    [60, 28, 52, 20, 62, 30, 54, 22],
                    [3, 35, 11, 43, 1, 33, 9, 41],
                    [51, 19, 59, 27, 49, 17, 57, 25],
                    [15, 47, 7, 39, 13, 45, 5, 37],
                    [63, 31, 55, 23, 61, 29, 53, 21],
                ],
                dtype=np.float32,
            )
            / 64.0
        )
    else:
        raise FrameError(f"Unsupported threshold matrix size: {threshold_matrix_size}")

    matrix_h, matrix_w = bayer.shape

    # Create threshold map by tiling the Bayer matrix
    threshold_map = np.tile(
        bayer, ((height + matrix_h - 1) // matrix_h, (width + matrix_w - 1) // matrix_w)
    )
    threshold_map = threshold_map[:height, :width]

    # Apply dithering
    return gray_image > threshold_map


def error_diffusion_floyd_steinberg(gray_image: np.ndarray) -> np.ndarray:
    """
    Apply Floyd-Steinberg error diffusion dithering.

    Args:
        gray_image: Grayscale image as float array (0.0 to 1.0)

    Returns:
        Binary image as boolean array
    """
    if not isinstance(gray_image, np.ndarray):
        raise FrameError(f"Image must be numpy array, got {type(gray_image)}")
    if gray_image.ndim != 2:
        raise FrameError(f"Image must be 2D, got {gray_image.ndim}D")
    if gray_image.dtype not in [np.float32, np.float64]:
        raise FrameError(f"Image must be float, got {gray_image.dtype}")

    # Work on a copy to avoid modifying input
    image = gray_image.copy().astype(np.float32)
    height, width = image.shape
    binary = np.zeros((height, width), dtype=bool)

    for y in range(height):
        for x in range(width):
            old_pixel = image[y, x]
            new_pixel = 1.0 if old_pixel > 0.5 else 0.0
            binary[y, x] = new_pixel > 0.5

            error = old_pixel - new_pixel

            # Distribute error to neighbors (Floyd-Steinberg weights)
            if x + 1 < width:
                image[y, x + 1] += error * 7 / 16
            if y + 1 < height:
                if x > 0:
                    image[y + 1, x - 1] += error * 3 / 16
                image[y + 1, x] += error * 5 / 16
                if x + 1 < width:
                    image[y + 1, x + 1] += error * 1 / 16

    return binary


def simple_threshold(gray_image: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    """
    Simple threshold conversion without dithering.

    Args:
        gray_image: Grayscale image as float array (0.0 to 1.0)
        threshold: Threshold value (0.0 to 1.0)

    Returns:
        Binary image as boolean array
    """
    if not isinstance(gray_image, np.ndarray):
        raise FrameError(f"Image must be numpy array, got {type(gray_image)}")
    if not 0 <= threshold <= 1:
        raise FrameError(f"Threshold must be 0-1, got {threshold}")

    return gray_image > threshold
