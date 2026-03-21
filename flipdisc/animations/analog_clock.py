"""Analog clock animation with round face, hour markers, and two hands."""

import math
from datetime import datetime
from typing import override

import numpy as np

from .base import Animation


def _draw_line(
    frame: np.ndarray, x0: float, y0: float, x1: float, y1: float
) -> None:
    """Draw a 1px line using Bresenham's algorithm."""
    h, w = frame.shape
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    steps = int(max(dx, dy))
    if steps == 0:
        return

    xs = (x1 - x0) / steps
    ys = (y1 - y0) / steps

    i = np.arange(steps + 1)
    px = np.round(x0 + i * xs).astype(int)
    py = np.round(y0 + i * ys).astype(int)
    valid = (px >= 0) & (px < w) & (py >= 0) & (py < h)
    frame[py[valid], px[valid]] = 1.0


class AnalogClockAnimation(Animation):
    """Analog clock showing current system time with hour/minute hands."""

    def __init__(self, width: int, height: int):
        super().__init__(width, height, processing_steps=("binarize",))

        self.cx = (width - 1) / 2  # 13.5 for 28px
        self.cy = (height - 1) / 2
        self.radius = 12.5
        self.minute_hand_length = 10.0
        self.hour_hand_length = 7.0

        # Pre-compute the static clock face (circle + markers)
        self._face = self._build_face()

    def _build_face(self) -> np.ndarray:
        """Render circle outline and hour markers to a cached array."""
        face = np.zeros((self.height, self.width), dtype=np.float32)

        # Draw circle outline via distance-from-center threshold
        yy, xx = np.mgrid[0 : self.height, 0 : self.width]
        dist = np.sqrt((xx - self.cx) ** 2 + (yy - self.cy) ** 2)
        circle_mask = (dist >= self.radius - 0.5) & (dist <= self.radius + 0.5)
        face[circle_mask] = 1.0

        # Draw hour markers
        for h in range(12):
            angle = 2 * math.pi * h / 12
            sin_a = math.sin(angle)
            cos_a = math.cos(angle)

            if h % 3 == 0:
                # Major markers (12, 3, 6, 9): 2px radial bars inward
                outer_r = self.radius - 1.0
                inner_r = self.radius - 2.5
                _draw_line(
                    face,
                    self.cx + outer_r * sin_a,
                    self.cy - outer_r * cos_a,
                    self.cx + inner_r * sin_a,
                    self.cy - inner_r * cos_a,
                )
            else:
                # Minor markers: 1px dot just inside the circle
                dot_r = self.radius - 2.0
                px = int(round(self.cx + dot_r * sin_a))
                py = int(round(self.cy - dot_r * cos_a))
                if 0 <= px < self.width and 0 <= py < self.height:
                    face[py, px] = 1.0

        return face

    @override
    def step(self, dt: float) -> None:
        self.current_time += dt

    @override
    def render_gray(self) -> np.ndarray:
        frame = self._face.copy()

        now = datetime.now()
        h = now.hour % 12
        m = now.minute

        # Hour hand — moves smoothly between hours based on minute
        hour_angle = 2 * math.pi * (h + m / 60) / 12
        _draw_line(
            frame,
            self.cx,
            self.cy,
            self.cx + self.hour_hand_length * math.sin(hour_angle),
            self.cy - self.hour_hand_length * math.cos(hour_angle),
        )

        # Minute hand
        minute_angle = 2 * math.pi * m / 60
        _draw_line(
            frame,
            self.cx,
            self.cy,
            self.cx + self.minute_hand_length * math.sin(minute_angle),
            self.cy - self.minute_hand_length * math.cos(minute_angle),
        )

        return frame
