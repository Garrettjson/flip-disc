"""Weather icon animation — internal sub-animation for WeatherAnimation.

Not registered in the public registry. Loads pixel-art weather icons from
assets/images/weather/ BMPs and renders them full-canvas. Precipitation
conditions (snow) overlay animated particle effects on top of cloud.bmp.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import ClassVar, override

import numpy as np
from skimage.io import imread

from .base import Animation
from .precipitation import WMO_RAIN_PRESETS, RainEffect, SnowEffect

_ICONS_DIR = Path(__file__).resolve().parents[2] / "assets" / "images" / "weather"

# Map condition strings to BMP filenames
_CONDITION_FILES: dict[str, str] = {
    "sunny": "sun.bmp",
    "partly_cloudy": "cloud.bmp",
    "cloudy": "cloud.bmp",
    "rain": "cloud.bmp",
    "snow": "cloud.bmp",
    "thunderstorm": "thunderstorm.bmp",
    "fog": "fog.bmp",
    "moon": "moon.bmp",
    "sunrise": "sunrise.bmp",
}

# Conditions that use animated precipitation instead of a static BMP
_PRECIP_CONDITIONS = {"snow", "rain"}

_CONDITIONS = set(_CONDITION_FILES.keys())
_FALLBACK = "cloudy"

# Moon disc rendering constants — matches existing moon.bmp bounding box
_MOON_CENTER = (8, 21)  # (row, col)
_MOON_RADIUS = 7


_MIN_PHASE = 0.13  # minimum crescent width — readable on low-res display


def _render_moon(canvas: np.ndarray, phase: float) -> None:
    """Draw a procedural moon disc with phase-based shadow mask.

    Args:
        canvas: (H, W) float32 array to draw into.
        phase: Moon phase in [0.0, 1.0). 0=new, 0.5=full.
    """
    # Clamp so even a new moon shows a thin 1px crescent
    phase = max(_MIN_PHASE, min(phase, 1.0 - _MIN_PHASE))

    cy, cx = _MOON_CENTER
    r = _MOON_RADIUS

    # Terminator offset: cos maps phase to how much of each row is lit.
    # phase=0 -> cos(0)=1 -> fully shadowed (new moon)
    # phase=0.25 -> cos(pi/2)=0 -> half lit (first quarter)
    # phase=0.5 -> cos(pi)=-1 -> fully lit (full moon)
    terminator = math.cos(phase * 2.0 * math.pi)

    for row in range(cy - r, cy + r + 1):
        if row < 0 or row >= canvas.shape[0]:
            continue
        # Half-width of the disc at this row
        dy = row - cy
        half_w_sq = r * r - dy * dy
        if half_w_sq < 0:
            continue
        half_w = math.sqrt(half_w_sq)
        col_left = cx - half_w
        col_right = cx + half_w

        # Terminator x position: splits the disc into lit and shadow.
        # For waning, negate so the terminator sweeps right-to-left.
        if phase <= 0.5:
            term_x = cx + terminator * half_w
        else:
            term_x = cx - terminator * half_w

        for col in range(max(0, int(col_left)), min(canvas.shape[1], int(col_right) + 1)):
            # Check pixel is inside the disc (circle test)
            if (col - cx) ** 2 + dy**2 > r * r:
                continue

            if phase <= 0.5:
                # Waxing: right side lights up first
                if col >= term_x:
                    canvas[row, col] = 1.0
            # Waning: left side stays lit last
            elif col <= term_x:
                canvas[row, col] = 1.0


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
        self._precip: SnowEffect | RainEffect | None = None
        self._moon_phase: float = 0.5  # default: full moon

    @override
    def configure(self, **params) -> None:
        super().configure(**params)
        spawn_rate = params.get("spawn_rate")
        fall_speed = params.get("fall_speed")
        droplet_size = params.get("droplet_size")
        wmo_code = params.get("wmo_code")

        if "moon_phase" in params:
            self._moon_phase = float(params["moon_phase"])

        if "condition" in params:
            cond = str(params["condition"])
            self._condition = cond if cond in _CONDITIONS else _FALLBACK

            if self._condition in _PRECIP_CONDITIONS:
                icon = self.ICONS[self._condition]
                cols_range, bottom_row = _cloud_bounds(icon)

                if self._condition == "rain":
                    # Look up WMO preset defaults, then let explicit params override
                    preset = (
                        WMO_RAIN_PRESETS.get(wmo_code, {})
                        if wmo_code is not None
                        else {}
                    )
                    self._precip = RainEffect(
                        cloud_cols_range=cols_range,
                        spawn_y=bottom_row + 1,
                        max_y=self.height - 1,
                        spawn_rate=spawn_rate
                        if spawn_rate is not None
                        else preset.get("spawn_rate", 3.0),
                        fall_speed=fall_speed
                        if fall_speed is not None
                        else preset.get("fall_speed", 14.0),
                        droplet_size=int(droplet_size)
                        if droplet_size is not None
                        else preset.get("droplet_size", 2),
                    )
                else:
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
            if droplet_size is not None:
                precip_params["droplet_size"] = droplet_size
            if precip_params:
                self._precip.configure(**precip_params)

    @override
    def step(self, dt: float) -> None:
        self.current_time += dt
        if self._precip is not None:
            self._precip.step(dt)

    @override
    def render_gray(self) -> np.ndarray:
        canvas = np.zeros((self.height, self.width), dtype=np.float32)

        if self._condition == "moon":
            _render_moon(canvas, self._moon_phase)
        else:
            icon = self.ICONS[self._condition]
            ih, iw = icon.shape
            h = min(self.height, ih)
            w = min(self.width, iw)
            canvas[:h, :w] = icon[:h, :w]

        if self._precip is not None:
            self._precip.render(canvas)
        return canvas
