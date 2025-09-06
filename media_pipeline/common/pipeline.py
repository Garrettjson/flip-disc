from __future__ import annotations

from typing import Callable, List

import numpy as np

BLACK = 255

Array = np.ndarray
StepFn = Callable[[Array], Array]


def _ensure_uint8(arr: Array) -> Array:
    # Accept lists or ndarrays; coerce to uint8 with clipping
    a = np.asarray(arr)
    if a.dtype != np.uint8:
        a = np.clip(a, 0, 255).astype(np.uint8, copy=False)
    return a


def _op_threshold(value: int) -> StepFn:
    v = int(max(0, min(BLACK, value)))

    def step(a: Array) -> Array:
        a8 = _ensure_uint8(a)
        return (a8 > v).astype(np.uint8)

    return step


def _op_invert() -> StepFn:
    def step(a: Array) -> Array:
        a8 = _ensure_uint8(a)
        # If already binary 0/1, flip to 1/0; otherwise grayscale invert
        mx = int(a8.max()) if a8.size > 0 else 0
        mn = int(a8.min()) if a8.size > 0 else 0
        if mn >= 0 and mx <= 1:
            return (1 - a8).astype(np.uint8)
        return (BLACK - a8).astype(np.uint8)

    return step


def _op_flip_h() -> StepFn:
    def step(a: Array) -> Array:
        return np.flip(a, axis=1)

    return step


def _op_flip_v() -> StepFn:
    def step(a: Array) -> Array:
        return np.flip(a, axis=0)

    return step


def _op_rotate180() -> StepFn:
    def step(a: Array) -> Array:
        return np.rot90(a, 2)

    return step


class Pipeline:
    """Fluent, chainable image pipeline.

    Usage:
      p = Pipeline().threshold(140).invert()
      out = p(img)

    Notes:
      - Steps are applied in the order added.
      - All ops are width×height preserving and vectorized (NumPy).
    """

    def __init__(self) -> None:
        self._steps: List[StepFn] = []

    # Chainable ops
    def threshold(self, value: int) -> "Pipeline":
        self._steps.append(_op_threshold(value))
        return self

    def invert(self) -> "Pipeline":
        self._steps.append(_op_invert())
        return self

    def flip_h(self) -> "Pipeline":
        self._steps.append(_op_flip_h())
        return self

    def flip_v(self) -> "Pipeline":
        self._steps.append(_op_flip_v())
        return self

    def rotate180(self) -> "Pipeline":
        self._steps.append(_op_rotate180())
        return self

    # Apply
    def apply(self, a: Array) -> Array:
        out = a
        for fn in self._steps:
            out = fn(out)
        return out

    __call__ = apply

    # No from_config: use chainable builder explicitly in workers

