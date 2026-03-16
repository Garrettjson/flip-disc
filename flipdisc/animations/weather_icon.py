"""Weather icon animation — internal sub-animation for WeatherAnimation.

Not registered in the public registry. Loads pixel-art weather icons from
assets/images/weather/ BMPs and renders them full-canvas.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import numpy as np
from skimage.io import imread

from .base import Animation

_ICONS_DIR = Path(__file__).resolve().parents[2] / "assets" / "images" / "weather"

# Map condition strings to BMP filenames
_CONDITION_FILES: dict[str, str] = {
    "sunny": "sun.bmp",
    "partly_cloudy": "cloud.bmp",
    "cloudy": "cloud.bmp",
    "rain": "rain.bmp",
    "snow": "snow.bmp",
    "thunderstorm": "thunderstorm.bmp",
    "fog": "fog.bmp",
    "moon": "moon.bmp",
    "sunrise": "sunrise.bmp",
}

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


class WeatherIconAnimation(Animation):
    """Displays a static weather condition icon loaded from a BMP file.

    Internal use only — not registered in the public animation registry.
    Used as a layer within WeatherAnimation.

    Configure with:
        condition — one of: sunny, partly_cloudy, cloudy, rain, snow,
                    thunderstorm, fog, moon, sunrise  (default: cloudy)
    """

    ICONS: ClassVar[dict[str, np.ndarray]] = _build_icons()

    def __init__(self, width: int, height: int):
        super().__init__(width, height, processing_steps=("binarize",))
        self._condition = _FALLBACK

    def configure(self, **params) -> None:
        super().configure(**params)
        if "condition" in params:
            cond = str(params["condition"])
            self._condition = cond if cond in _CONDITIONS else _FALLBACK

    def step(self, dt: float) -> None:
        self.current_time += dt

    def render_gray(self) -> np.ndarray:
        icon = self.ICONS[self._condition]
        canvas = np.zeros((self.height, self.width), dtype=np.float32)
        ih, iw = icon.shape
        h = min(self.height, ih)
        w = min(self.width, iw)
        canvas[:h, :w] = icon[:h, :w]
        return canvas
