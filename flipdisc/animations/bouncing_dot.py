"""Simple bouncing dot animation."""

import math

import numpy as np

from .base import Animation, register_animation


@register_animation("bouncing_dot")
class BouncingDot(Animation):
    """Simple bouncing dot with physics."""

    def __init__(self, width: int, height: int):
        super().__init__(width, height)

        # Dot state
        self.x = width / 2
        self.y = height / 2
        self.vx = 30.0  # pixels per second
        self.vy = 20.0

        # Visual parameters
        self.radius = 2.0
        self.trail_length = 8
        self.trail_positions = []

        # Physics
        self.gravity = 0.0  # No gravity by default
        self.bounce_damping = 0.95

    def configure(self, **params):
        """Configure bouncing dot parameters."""
        super().configure(**params)

        if "speed" in params:
            speed = float(params["speed"])
            angle = math.atan2(self.vy, self.vx)
            self.vx = speed * math.cos(angle)
            self.vy = speed * math.sin(angle)
        if "gravity" in params:
            self.gravity = float(params["gravity"])
        if "radius" in params:
            self.radius = float(params["radius"])
        if "trail_length" in params:
            self.trail_length = int(params["trail_length"])

    def step(self, dt: float) -> None:
        """Advance dot physics."""
        self.current_time += dt

        # Apply gravity
        self.vy += self.gravity * dt

        # Update position
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Bounce off walls
        if self.x <= self.radius or self.x >= self.width - self.radius:
            self.vx *= -self.bounce_damping
            self.x = max(self.radius, min(self.width - self.radius, self.x))

        if self.y <= self.radius or self.y >= self.height - self.radius:
            self.vy *= -self.bounce_damping
            self.y = max(self.radius, min(self.height - self.radius, self.y))

        # Update trail
        self.trail_positions.append((self.x, self.y))
        if len(self.trail_positions) > self.trail_length:
            self.trail_positions.pop(0)

    def render_gray(self) -> np.ndarray:
        """Render bouncing dot to grayscale."""
        frame = np.zeros((self.height, self.width), dtype=np.float32)

        # Draw trail (fading)
        for i, (x, y) in enumerate(self.trail_positions[:-1]):
            intensity = (i + 1) / len(self.trail_positions) * 0.5
            radius = self.radius * 0.7
            self._draw_circle(frame, x, y, radius, intensity)

        # Draw main dot
        if self.trail_positions:
            x, y = self.trail_positions[-1]
            self._draw_circle(frame, x, y, self.radius, 1.0)

        return frame

    def _draw_circle(
        self, frame: np.ndarray, cx: float, cy: float, radius: float, intensity: float
    ):
        """Draw anti-aliased circle."""
        y_min = max(0, int(cy - radius - 1))
        y_max = min(self.height, int(cy + radius + 2))
        x_min = max(0, int(cx - radius - 1))
        x_max = min(self.width, int(cx + radius + 2))

        for y in range(y_min, y_max):
            for x in range(x_min, x_max):
                dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
                if dist <= radius + 0.5:  # Include edge pixels for anti-aliasing
                    # Anti-aliasing: fade based on distance from edge
                    alpha = 1.0 if dist <= radius - 0.5 else max(0, radius + 0.5 - dist)
                    frame[y, x] = max(frame[y, x], intensity * alpha)
