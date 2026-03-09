"""Static image animation — renders a single PNG frame on the display."""

from __future__ import annotations

import numpy as np
from skimage.io import imread

from flipdisc.animations.clip import _blit_fit

from .base import Animation, register_animation


@register_animation("image")
class ImageAnimation(Animation):
    """Displays a static PNG image, center-fitted to the layer dimensions.

    The image is loaded and binarized at configure time. Updating ``src``
    swaps the image live without restarting the animation::

        POST /anim/image
        {"src": "assets/images/cloud.png"}

        POST /animations/configure
        {"layer.icon.src": "assets/images/sun.png"}
    """

    def __init__(self, width: int, height: int):
        super().__init__(width, height, processing_steps=("binarize",))
        self._frame: np.ndarray | None = None

    def configure(self, **params) -> None:
        super().configure(**params)
        if "src" in params:
            self._frame = imread(str(params["src"]), as_gray=True).astype(np.float32)

    def step(self, dt: float) -> None:
        self.current_time += dt

    def render_gray(self) -> np.ndarray:
        canvas = np.zeros((self.height, self.width), dtype=np.float32)
        if self._frame is not None:
            _blit_fit(canvas, self._frame, "center")
        return canvas
