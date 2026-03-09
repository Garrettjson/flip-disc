"""Clip playback animation — plays a pre-rendered .npz frame sequence."""

from __future__ import annotations

import numpy as np

from flipdisc.clips.loader import ClipData, load_clip

from .base import Animation, register_animation


def _blit_fit(canvas: np.ndarray, src: np.ndarray, mode: str) -> None:
    """Blit ``src`` onto ``canvas`` using the specified fit mode.

    Args:
        canvas: Destination float32 array (H, W).
        src: Source float32 array (Hs, Ws).
        mode: "center" (pad/crop), "stretch" (nearest-neighbor), or "tile".
    """
    ch, cw = canvas.shape
    sh, sw = src.shape

    if mode == "center":
        dst_y = max(0, (ch - sh) // 2)
        dst_x = max(0, (cw - sw) // 2)
        src_y = max(0, (sh - ch) // 2)
        src_x = max(0, (sw - cw) // 2)
        h = min(ch - dst_y, sh - src_y)
        w = min(cw - dst_x, sw - src_x)
        if h > 0 and w > 0:
            canvas[dst_y : dst_y + h, dst_x : dst_x + w] = src[
                src_y : src_y + h, src_x : src_x + w
            ]

    elif mode == "stretch":
        y_idx = (np.arange(ch) * sh // max(ch, 1)).clip(0, sh - 1)
        x_idx = (np.arange(cw) * sw // max(cw, 1)).clip(0, sw - 1)
        canvas[:] = src[np.ix_(y_idx, x_idx)]

    elif mode == "tile":
        for dy in range(0, ch, sh):
            for dx in range(0, cw, sw):
                h = min(sh, ch - dy)
                w = min(sw, cw - dx)
                canvas[dy : dy + h, dx : dx + w] = src[:h, :w]


@register_animation("clip")
class ClipAnimation(Animation):
    """Plays a pre-rendered clip (.npz) full-screen on the display.

    Configure with ``name`` (required) to select a clip from clips.toml.

    API usage::

        POST /anim/clip
        {"name": "rain", "loop": true}
    """

    def __init__(self, width: int, height: int):
        super().__init__(width, height, processing_steps=None)
        self._clip: ClipData | None = None
        self._fps: float = 20.0
        self._loop: bool = True
        self._frame_idx: float = 0.0
        self._fit_mode: str = "center"

    def configure(self, **params) -> None:
        super().configure(**params)
        if "name" in params:
            self._clip = load_clip(params["name"])
            self._fps = self._clip.fps
            self._loop = self._clip.loop
            self._frame_idx = 0.0
            self._completed = False
            self._fit_mode = "center"
        if "fps_override" in params:
            self._fps = float(params["fps_override"])
        if "loop" in params:
            self._loop = bool(params["loop"])
        if "fit_mode" in params:
            self._fit_mode = str(params["fit_mode"])

    def step(self, dt: float) -> None:
        self.current_time += dt
        if self._clip is None:
            return

        self._frame_idx += self._fps * dt
        n = len(self._clip.frames)

        if self._loop:
            if n > 0:
                self._frame_idx %= n
        elif self._frame_idx >= n:
            self._frame_idx = float(n - 1)
            self._completed = True

    def render_gray(self) -> np.ndarray:
        canvas = np.zeros((self.height, self.width), dtype=np.float32)
        if self._clip is None:
            return canvas

        src = self._clip.frames[int(self._frame_idx)].astype(np.float32)
        _blit_fit(canvas, src, self._fit_mode)
        return canvas

    def reset(self, seed: int | None = None) -> None:
        super().reset(seed)
        self._frame_idx = 0.0
