"""Simple bouncing dot animation."""

import numpy as np

from .base import Animation, register_animation


@register_animation("bouncing_dot")
class BouncingDot(Animation):
    """Simple bouncing dot"""

    def __init__(self, width: int, height: int):
        super().__init__(width, height, output_format="binary", processing_steps=("binarize",))

        # Dot position (discrete pixel coordinates)
        self.x = 2
        self.y = 5

        # Direction (velocity in pixels per step)
        self.dx = 1
        self.dy = 2

    def configure(self, **params):
        """Configure bouncing dot parameters."""
        super().configure(**params)

        if "start_x" in params:
            self.x = max(0, min(int(params["start_x"]), self.width - 1))
        if "start_y" in params:
            self.y = max(0, min(int(params["start_y"]), self.height - 1))
        if "speed_x" in params:
            self.dx = int(params["speed_x"])
        if "speed_y" in params:
            self.dy = int(params["speed_y"])

    def step(self, dt: float) -> None:
        """Advance dot position (simplified discrete movement)."""
        self.current_time += dt

        # Clamp position in case display size changed
        self.x = max(0, min(self.x, self.width - 1))
        self.y = max(0, min(self.y, self.height - 1))

        # Advance position
        self.x += self.dx
        self.y += self.dy

        # Bounce off walls
        if self.x <= 0 or self.x >= self.width - 1:
            self.dx *= -1
            self.x = max(0, min(self.x, self.width - 1))

        if self.y <= 0 or self.y >= self.height - 1:
            self.dy *= -1
            self.y = max(0, min(self.y, self.height - 1))

    def render_gray(self) -> np.ndarray:
        """Render bouncing dot as single pixel."""
        frame = np.zeros((self.height, self.width), dtype=np.float32)

        # Set single pixel at current position
        frame[self.y, self.x] = 1.0

        return frame
