"""Core shared types for the flipdisc application."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Frame:
    """A single animation frame with timing metadata.

    - seq: monotonically increasing sequence number (assigned by server)
    - produced_ts: wall-clock time when the frame was generated (worker)
    - target_ts: ideal display time for pacing; may be None if unknown
    - bits: 2D numpy boolean array of shape (height, width)
    """

    seq: int
    produced_ts: float
    target_ts: float | None
    bits: np.ndarray

