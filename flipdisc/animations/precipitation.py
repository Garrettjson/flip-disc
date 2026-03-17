"""Precipitation particle effects for weather animations.

SnowEffect renders falling snowflake particles over a cloud icon.
Future: RainEffect, ThunderEffect, FogEffect.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np

# Snowflake shapes: tuples of (row, col) offsets from the particle origin.
# 1-piece single pixel
_SNOW_1 = ((0, 0),)
# 2-piece diagonal pairs
_SNOW_2A = ((0, 1), (1, 0))
_SNOW_2B = ((0, 0), (1, 1))
# 3-piece zigzag variants
_SNOW_3A = ((0, 1), (1, 0), (1, 2))
_SNOW_3B = ((0, 0), (0, 2), (1, 1))
_SNOW_3C = ((0, 0), (1, 1), (2, 0))
_SNOW_3D = ((0, 1), (1, 0), (2, 1))

_SNOW_SHAPES = [_SNOW_1, _SNOW_2A, _SNOW_2B, _SNOW_3A, _SNOW_3B, _SNOW_3C, _SNOW_3D]


@dataclass
class SnowParticle:
    x: int
    y: int
    shape: tuple[tuple[int, int], ...]


class SnowEffect:
    """Falling snow particle system.

    Spawns snowflake particles from the cloud base that fall straight down.
    Each snowflake is a small 2-3 pixel diagonal/zigzag shape.

    All particles advance exactly 1px at the same time via a shared fall
    timer, so spacing between snowflakes stays perfectly uniform.
    """

    def __init__(
        self,
        cloud_cols_range: tuple[int, int],
        spawn_y: int,
        max_y: int,
        spawn_rate: float = 2.0,
        fall_speed: float = 6.0,
    ):
        self._col_min, self._col_max = cloud_cols_range
        self._spawn_y = spawn_y
        self._max_y = max_y
        self._spawn_rate = spawn_rate
        self._fall_speed = fall_speed
        self._particles: list[SnowParticle] = []
        self._spawn_timer: float = 0.0
        self._fall_timer: float = 0.0
        self._last_spawn_x: int | None = None
        self._rng = random.Random()

    def step(self, dt: float) -> None:
        # Advance all particles in lockstep: 1px per tick
        self._fall_timer += dt
        fall_interval = 1.0 / self._fall_speed
        while self._fall_timer >= fall_interval:
            self._fall_timer -= fall_interval
            for p in self._particles:
                p.y += 1

        # Cull off-screen particles
        self._particles = [p for p in self._particles if p.y <= self._max_y + 2]

        # Spawn new particles
        if self._spawn_rate <= 0:
            return
        self._spawn_timer += dt
        interval = 1.0 / self._spawn_rate
        while self._spawn_timer >= interval:
            self._spawn_timer -= interval
            self._spawn_particle()

    def _spawn_particle(self) -> None:
        rng = self._rng
        shape = rng.choice(_SNOW_SHAPES)

        # Pick x within cloud range, at least 2px from last spawn
        col_min, col_max = self._col_min, self._col_max
        candidates = list(range(col_min, col_max + 1))
        if self._last_spawn_x is not None:
            candidates = [c for c in candidates if abs(c - self._last_spawn_x) >= 2]
            if not candidates:
                candidates = list(range(col_min, col_max + 1))

        x = rng.choice(candidates)
        self._last_spawn_x = x

        self._particles.append(
            SnowParticle(x=x, y=self._spawn_y, shape=shape)
        )

    def render(self, canvas: np.ndarray) -> None:
        h, w = canvas.shape
        for p in self._particles:
            for dr, dc in p.shape:
                r = p.y + dr
                c = p.x + dc
                if 0 <= r < h and 0 <= c < w:
                    canvas[r, c] = max(canvas[r, c], 1.0)

    def configure(self, **params) -> None:
        if "spawn_rate" in params:
            self._spawn_rate = float(params["spawn_rate"])
        if "fall_speed" in params:
            self._fall_speed = float(params["fall_speed"])

    def reset(self) -> None:
        self._particles.clear()
        self._spawn_timer = 0.0
        self._fall_timer = 0.0
        self._last_spawn_x = None
