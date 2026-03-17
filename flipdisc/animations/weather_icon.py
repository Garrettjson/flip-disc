"""Weather icon animation — internal sub-animation for WeatherAnimation.

Not registered in the public registry. Loads pixel-art weather icons from
assets/images/weather/ BMPs and renders them full-canvas. Precipitation
conditions (snow) overlay animated particle effects on top of cloud.bmp.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, override

import numpy as np
from skimage.io import imread

from .base import Animation
from .precipitation import SnowEffect

_ICONS_DIR = Path(__file__).resolve().parents[2] / "assets" / "images" / "weather"

# Map condition strings to BMP filenames
_CONDITION_FILES: dict[str, str] = {
    "sunny": "sun.bmp",
    "partly_cloudy": "cloud.bmp",
    "cloudy": "cloud.bmp",
    "rain": "rain.bmp",
    "snow": "cloud.bmp",
    "thunderstorm": "thunderstorm.bmp",
    "fog": "fog.bmp",
    "moon": "moon.bmp",
    "sunrise": "sunrise.bmp",
}

# Conditions that use animated precipitation instead of a static BMP
_PRECIP_CONDITIONS = {"snow"}

_CONDITIONS = set(_CONDITION_FILES.keys())
_FALLBACK = "cloudy"


def _build_icons() -> dict[str, np.ndarray]:
    icons: dict[str, np.ndarray] = {}
    loaded: dict[str, np.ndarray] = {}

    for condition, filename in _CONDITION_FILES.items():
        path = _ICONS_DIR / filename
        if filename not in loaded:
            loaded[filename] = imread(str(path), as_gray=True).astype(np.float32)
        icons[condition] = loaded[filename]

    return icons


def _cloud_bounds(icon: np.ndarray) -> tuple[tuple[int, int], int]:
    """Find the horizontal extent and bottom row of the cloud in the icon.

    Returns:
        (col_min, col_max), bottom_row
    """
    # Scan from bottom up to find the lowest row with lit pixels
    for row in range(icon.shape[0] - 1, -1, -1):
        cols = np.where(icon[row] > 0.5)[0]
        if len(cols) > 0:
            return (int(cols[0]), int(cols[-1])), row
    # Fallback: full width, middle row
    return (0, icon.shape[1] - 1), icon.shape[0] // 2


class WeatherIconAnimation(Animation):
    """Displays a weather condition icon, with optional animated precipitation.

    Internal use only — not registered in the public animation registry.
    Used as a layer within WeatherAnimation.

    Configure with:
        condition  — one of: sunny, partly_cloudy, cloudy, rain, snow,
                     thunderstorm, fog, moon, sunrise  (default: cloudy)
        spawn_rate — precipitation particles per second (default 2.0)
        fall_speed — precipitation fall speed in px/sec (default 6.0)
    """

    ICONS: ClassVar[dict[str, np.ndarray]] = _build_icons()

    def __init__(self, width: int, height: int):
        super().__init__(width, height, processing_steps=("binarize",))
        self._condition = _FALLBACK
        self._precip: SnowEffect | None = None

    @override
    def configure(self, **params) -> None:
        super().configure(**params)
        spawn_rate = params.get("spawn_rate")
        fall_speed = params.get("fall_speed")

        if "condition" in params:
            cond = str(params["condition"])
            self._condition = cond if cond in _CONDITIONS else _FALLBACK

            if self._condition in _PRECIP_CONDITIONS:
                icon = self.ICONS[self._condition]
                cols_range, bottom_row = _cloud_bounds(icon)
                self._precip = SnowEffect(
                    cloud_cols_range=cols_range,
                    spawn_y=bottom_row + 1,
                    max_y=self.height - 1,
                    spawn_rate=spawn_rate if spawn_rate is not None else 2.0,
                    fall_speed=fall_speed if fall_speed is not None else 6.0,
                )
            else:
                self._precip = None
        elif self._precip is not None:
            precip_params = {}
            if spawn_rate is not None:
                precip_params["spawn_rate"] = spawn_rate
            if fall_speed is not None:
                precip_params["fall_speed"] = fall_speed
            if precip_params:
                self._precip.configure(**precip_params)

    @override
    def step(self, dt: float) -> None:
        self.current_time += dt
        if self._precip is not None:
            self._precip.step(dt)

    @override
    def render_gray(self) -> np.ndarray:
        icon = self.ICONS[self._condition]
        canvas = np.zeros((self.height, self.width), dtype=np.float32)
        ih, iw = icon.shape
        h = min(self.height, ih)
        w = min(self.width, iw)
        canvas[:h, :w] = icon[:h, :w]
        if self._precip is not None:
            self._precip.render(canvas)
        return canvas
