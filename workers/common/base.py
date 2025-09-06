from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, List, Literal, Optional, Union


"""
Worker SDK — Base Rendering Contract
===================================

Purpose
- Provide a minimal rendering contract (`WorkerBase`). A separate `WorkerRunner`
  handles orchestration via a WebSocket control channel (ticks + config), local
  preview, frame packing (RBM), and posting frames to the orchestrator.

Worker Contract
- Subclass `WorkerBase` and implement:
    render(t: float, display: DisplayInfo, cfg: dict) -> Frame2D | Iterable[Iterable[int]]
  where:
    - `t` is a monotonically increasing time since the worker started (seconds)
    - `display` has `width`, `height`, `fps` from the server’s `/config`
    - `cfg` is the latest per‑worker config dict from `/workers/:id/config`
  Return a Frame2D or a 2D iterable of integers 0/1. Default policy requires exact
  `height × width` dimensions; see Size Policy below.

Environment Variables
- `ORCH_URL`   : Base URL for orchestrator (default `http://localhost:8090`).
- `HEADLESS`   : When set to `1`, `true`, or `True`, disables the Tk preview.

Control Flow
- Orchestrator sends ticks and configuration over WebSocket `/workers/:id/ws`.
- Workers render on ticks and POST RBM frames to `/workers/:id/frame`.
- Orchestrator is the single source of truth for timing; it patches RBM
  `frame_duration_ms` based on target FPS when forwarding to the server.

Size Policy
- `strict` (default): frames must exactly match `display.height × display.width`.
  A mismatch raises a `ValueError` and the frame is not posted.
- `pad`: top‑left place the generated frame into a zeroed canvas and crop/pad
  to display bounds. Use for prototyping, but prefer strict for correctness.

Preview Behavior
- The runner attempts to create a Tk window via `workers.common.preview.make_preview`.
  If Tk is unavailable or `HEADLESS` is set, it uses a no‑op preview.

Timing & Pacing
- The orchestrator paces rendering by sending WS ticks; workers should use `t`
  (seconds since worker start) for time‑based animation.
"""


@dataclass
class DisplayInfo:
    """Display metadata supplied by the server.

    Attributes:
    - width: Logical canvas width in pixels.
    - height: Logical canvas height in pixels.
    - fps: Target frames per second configured on the server (authoritative pacing).
    """

    width: int
    height: int
    fps: int


@dataclass
class Frame2D:
    """Simple container for a binary 2D frame (0/1 ints).

    Use this to make worker return types explicit and self-documenting.

    Attributes:
    - data: 2D list of ints (0/1), shape = [height][width].
    """

    data: List[List[int]]

    @property
    def height(self) -> int:
        return len(self.data)

    @property
    def width(self) -> int:
        return len(self.data[0]) if self.data else 0

    def as_rows(self) -> List[List[int]]:
        """Return the underlying 2D list-of-lists representation."""
        return self.data

    @staticmethod
    def zeros(height: int, width: int) -> "Frame2D":
        """Construct a zero-initialized frame with the given dimensions."""
        return Frame2D([[0 for _ in range(width)] for _ in range(height)])

    @staticmethod
    def from_rows(rows: Iterable[Iterable[object]]) -> "Frame2D":
        """Build a Frame2D from any row-iterable (e.g., numpy array, lists).

        Values are coerced to 0/1 ints.
        """
        return Frame2D([[1 if v else 0 for v in row] for row in rows])


# Type aliases for clarity in signatures
FrameRows = Iterable[Iterable[int]]
FrameLike = Union[Frame2D, FrameRows]


class WorkerBase(ABC):
    """
    Minimal harness for flip-disc workers.

    Subclass implements render(t, display, cfg) and the runner handles:
    - WebSocket control channel (ticks + config) with the orchestrator
    - local preview window (Tk when available; HEADLESS=1 disables)
    - RBM packaging and posting frames to orchestrator (/workers/:id/frame)

    Env vars:
    - ORCH_URL: orchestrator base URL (default http://localhost:8090)
    - HEADLESS: set to 1/true to disable Tk preview
    """

    def __init__(
        self,
        worker_id: str,
        *,
        size_policy: Literal["strict", "pad"] = "strict",
        preview_scale: int = 20,
        preview_title: Optional[str] = None,
    ) -> None:
        self.worker_id = worker_id
        self.size_policy = size_policy
        self.preview_scale = preview_scale
        self.preview_title = preview_title or f"{worker_id} Preview"

    @abstractmethod
    def render(
        self, t: float, display: DisplayInfo, cfg: dict
    ) -> FrameLike:
        """Return a Frame2D or 2D 0/1 rows sized to the display (or smaller if size_policy allows)."""
        raise NotImplementedError

    # Optional hook for subclasses to react to config changes
    def on_config(self, display: DisplayInfo, cfg: dict) -> None:  # pragma: no cover - optional
        """Called when live config changes; subclasses may override if needed."""
        return None

    # ---- Harness ----

    def _coerce_frame_shape(
        self, frame: FrameLike, width: int, height: int
    ) -> List[List[int]]:
        """Normalize different frame return types and enforce the size policy.

        Accepts a Frame2D or an iterable of rows and returns a concrete
        height×width list-of-lists of 0/1 ints, either validating (strict)
        or padding/cropping (pad policy) as configured.
        """
        # Convert to list of lists of 0/1 ints
        if isinstance(frame, Frame2D):
            rows = [[1 if v else 0 for v in row] for row in frame.as_rows()]
        else:
            rows = [[1 if v else 0 for v in row] for row in frame]
        h = len(rows)
        w = len(rows[0]) if h > 0 else 0
        if self.size_policy == "strict":
            if h != height or w != width:
                raise ValueError(f"frame size {w}x{h} != display {width}x{height}")
            return rows
        # "pad" policy: top-left place + crop to display bounds
        out = [[0 for _ in range(width)] for _ in range(height)]
        mh = min(height, h)
        mw = min(width, w)
        for y in range(mh):
            src_row = rows[y]
            for x in range(mw):
                out[y][x] = 1 if src_row[x] else 0
        return out

    def run(self) -> None:
        """Delegate to WorkerRunner for WS-driven control and pacing."""
        from .runner import WorkerRunner

        WorkerRunner(self).run()
