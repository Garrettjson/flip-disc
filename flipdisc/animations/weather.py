"""Weather animation — iOS-style weather widget for the flip-disc display.

Shows a pixel-art weather icon (top-right) and current temperature text
(bottom-left overlay). Registered as "weather".

Configure with:
    temp      — numeric temperature (e.g. 72)
    condition — one of: sunny, partly_cloudy, cloudy, rain, snow,
                thunderstorm, fog
    unit      — "F" or "C" (default "F")
"""

from __future__ import annotations

from typing import Any, override

import numpy as np

from .base import register_animation
from .composed import ComposedAnimation
from .text import TextAnimation
from .weather_icon import WeatherIconAnimation

# Small degree symbol: 3×3 diamond
#  x
# x x
#  x
_DEGREE = np.array(
    [[0, 1, 0], [1, 0, 1], [0, 1, 0]],
    dtype=np.float32,
)


@register_animation("weather")
class WeatherAnimation(ComposedAnimation):
    """Weather widget: icon layer + temperature text overlay.

    Layout (28x28):
        - Icon: WeatherIconAnimation fills full canvas, placed top-right so the
          bottom-left region stays dark for the temperature text.
        - Temp: TextAnimation at x=1, y=height-8 (1px bottom pad), left-aligned.
          Shows the numeric value only; degree symbol + unit are blitted in
          render_gray so they sit flush against the number regardless of width.
        - Both layers blend with "add" (np.maximum).

    Example::

        POST /anim/weather
        {"temp": 72, "condition": "sunny", "unit": "F"}

        POST /animations/configure
        {"temp": 68, "condition": "cloudy"}
    """

    def __init__(self, width: int, height: int):
        super().__init__(width, height)
        self._show_degree = True
        icon = WeatherIconAnimation(width, height)
        icon.configure(condition="cloudy")
        temp = TextAnimation(width - 1, 7)
        temp.configure(text="--", mode="static", font="standard", align="left")
        self.compose(
            [
                (icon, {"id": "icon", "x": 0, "y": 0, "blend": "add"}),
                (temp, {"id": "temp", "x": 1, "y": height - 8, "blend": "add"}),
            ]
        )

    @override
    def configure(self, **params: Any) -> None:
        if "condition" in params:
            self._update_layer("icon", {"condition": params["condition"]})
        if "temp" in params:
            # Store number only — degree + unit drawn in render_gray
            self._update_layer("temp", {"text": str(int(params["temp"]))})
        if "show_degree" in params:
            self._show_degree = bool(params["show_degree"])
        super().configure(**params)

    @override
    def render_gray(self) -> np.ndarray:
        canvas = super().render_gray()

        if not self._show_degree:
            return canvas

        for layer in self._layers:
            if layer.id != "temp":
                continue
            text_img = layer.anim._text_image
            if text_img is None:
                break

            h, w = canvas.shape
            text_w = text_img.shape[1]

            # Degree symbol: 1px gap after number, raised 3px to act as superscript
            dx = layer.x + text_w + 1
            dy = layer.y - 2
            for dr in range(_DEGREE.shape[0]):
                for dc in range(_DEGREE.shape[1]):
                    r, c = dy + dr, dx + dc
                    if 0 <= r < h and 0 <= c < w:
                        canvas[r, c] = max(canvas[r, c], _DEGREE[dr, dc])
            break

        return canvas
