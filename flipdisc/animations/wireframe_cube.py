"""Rotating 3D wireframe cube animation."""

import math

import numpy as np

from .base import Animation, register_animation

# Unit cube vertices centered at origin
_VERTICES = np.array(
    [
        [-1, -1, -1],
        [+1, -1, -1],
        [+1, +1, -1],
        [-1, +1, -1],
        [-1, -1, +1],
        [+1, -1, +1],
        [+1, +1, +1],
        [-1, +1, +1],
    ],
    dtype=np.float64,
)

# 12 edges as pairs of vertex indices
_EDGES = [
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 0),  # back face
    (4, 5),
    (5, 6),
    (6, 7),
    (7, 4),  # front face
    (0, 4),
    (1, 5),
    (2, 6),
    (3, 7),  # connecting edges
]


def _rotation_matrix(angle_x: float, angle_y: float, angle_z: float) -> np.ndarray:
    """Build a combined rotation matrix from Euler angles (radians)."""
    cx, sx = math.cos(angle_x), math.sin(angle_x)
    cy, sy = math.cos(angle_y), math.sin(angle_y)
    cz, sz = math.cos(angle_z), math.sin(angle_z)

    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])

    return rz @ ry @ rx


@register_animation("wireframe_cube")
class WireframeCube(Animation):
    """Rotating 3D wireframe cube, oldschool demoscene style."""

    def __init__(self, width: int, height: int):
        super().__init__(width, height, processing_steps=("binarize",))

        self.size = 0.35  # cube size as fraction of display
        self.rotation_speed = 1.0  # radians per second
        self.axis_x = 1.0  # rotation weight per axis
        self.axis_y = 0.7
        self.axis_z = 0.3

        self.angle = 0.0

    def configure(self, **params):
        super().configure(**params)

        if "size" in params:
            self.size = max(0.1, min(0.5, float(params["size"])))
        if "rotation_speed" in params:
            self.rotation_speed = float(params["rotation_speed"])
        if "axis_x" in params:
            self.axis_x = float(params["axis_x"])
        if "axis_y" in params:
            self.axis_y = float(params["axis_y"])
        if "axis_z" in params:
            self.axis_z = float(params["axis_z"])

    def step(self, dt: float) -> None:
        self.current_time += dt
        self.angle += self.rotation_speed * dt

    def render_gray(self) -> np.ndarray:
        frame = np.zeros((self.height, self.width), dtype=np.float32)

        # Rotate vertices
        rot = _rotation_matrix(
            self.angle * self.axis_x,
            self.angle * self.axis_y,
            self.angle * self.axis_z,
        )
        rotated = _VERTICES @ rot.T

        # Weak perspective projection (z pushes things slightly smaller/larger)
        scale = min(self.width, self.height) * self.size
        cx, cy = self.width / 2, self.height / 2
        depth_scale = 6.0  # distance from camera; larger = flatter

        factor = depth_scale / (depth_scale + rotated[:, 2])  # (8,) broadcast
        projected = np.empty((8, 2))
        projected[:, 0] = cx + rotated[:, 0] * scale * factor
        projected[:, 1] = cy + rotated[:, 1] * scale * factor

        # Draw edges
        for i0, i1 in _EDGES:
            _draw_line(
                frame,
                projected[i0, 0],
                projected[i0, 1],
                projected[i1, 0],
                projected[i1, 1],
            )

        return frame


def _draw_line(frame: np.ndarray, x0: float, y0: float, x1: float, y1: float) -> None:
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
