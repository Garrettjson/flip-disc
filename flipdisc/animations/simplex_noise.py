"""Simplex noise animation."""

import numpy as np
from opensimplex import noise3array

from .base import Animation, register_animation


@register_animation("simplex_noise")
class SimplexNoise(Animation):
    """Animated simplex noise pattern."""

    def __init__(self, width: int, height: int):
        super().__init__(width, height, output_format="gray", processing_steps=("binarize",))

        # Parameters
        self.scale = 4.0  # Spatial scale of the noise
        self.step_size = 0.05  # Speed of animation
        self.i = 0.0  # Current time offset

        # Precompute coordinate arrays
        self.x = np.arange(width)
        self.y = np.arange(height)

    def configure(self, **params):
        """Configure simplex noise parameters."""
        super().configure(**params)

        if "scale" in params:
            self.scale = max(0.1, float(params["scale"]))
        if "step_size" in params:
            self.step_size = float(params["step_size"])

    def step(self, dt: float) -> None:
        """Advance noise animation through time."""
        self.current_time += dt
        self.i += self.step_size

    def render_gray(self) -> np.ndarray:
        """Render simplex noise to grayscale."""
        # Generate noise using noise3array
        arr = noise3array(self.x / self.scale, self.y / self.scale, np.array([self.i]))[0, :, :]

        # Map from [-1, 1] to [0, 1]
        frame = (arr + 1.0) / 2.0

        return frame.astype(np.float32)
