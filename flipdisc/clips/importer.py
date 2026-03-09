"""Dev utilities for importing clip data into .npz format.

Not imported by the server — use from scripts or tests only.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from skimage.io import imread

if TYPE_CHECKING:
    from flipdisc.animations.base import Animation


def import_clip_from_png_sequence(
    folder: str | Path,
    output_path: str | Path,
    threshold: float = 0.5,
) -> None:
    """Import a PNG image sequence into a compressed .npz clip file.

    Reads all .png files in ``folder`` (sorted lexicographically), binarizes
    each frame at ``threshold``, and saves them as a (N, H, W) bool array.
    Record the fps separately in ``clips.toml``.

    Args:
        folder: Directory containing sorted PNG frames.
        output_path: Destination .npz path.
        threshold: Binarization threshold in [0, 1].
    """
    folder = Path(folder)
    png_paths = sorted(folder.glob("*.png"))
    if not png_paths:
        raise ValueError(f"No .png files found in {folder}")

    frames: list[np.ndarray] = []
    for p in png_paths:
        img = imread(str(p), as_gray=True).astype(np.float32)
        frames.append(img > threshold)

    stacked = np.stack(frames, axis=0)  # (N, H, W) bool
    np.savez_compressed(str(output_path), frames=stacked)


def create_clip_from_animation(
    anim: Animation,
    n_frames: int,
    dt: float,
    output_path: str | Path,
) -> None:
    """Record a live animation to a .npz clip file.

    Steps the animation ``n_frames`` times and records each ``render_gray()``
    output, binarized at 0.5.

    Args:
        anim: Any Animation instance (already configured).
        n_frames: Number of frames to record.
        dt: Time step per frame in seconds.
        output_path: Destination .npz path.
    """
    frames: list[np.ndarray] = []
    for _ in range(n_frames):
        anim.step(dt)
        gray = anim.render_gray()
        frames.append(gray > 0.5)

    stacked = np.stack(frames, axis=0)  # (N, H, W) bool
    np.savez_compressed(str(output_path), frames=stacked)
