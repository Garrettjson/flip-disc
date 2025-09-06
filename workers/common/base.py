from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, List, Literal, Optional, Union, Iterator, Any, Callable

from .preview import make_preview
from .rbm import pack_bitmap_1bit, encode_rbm


"""
Worker SDK — Base Harness for Flip‑Disc Workers
================================================

Purpose
- Provide a minimal, reusable harness (`WorkerBase`) so workers only implement
  pixel generation while the harness handles discovery, preview, packing, and IO.

Worker Contract
- Subclass `WorkerBase` and implement ONE of:
    1) render(t: float, display: DisplayInfo, cfg: dict) -> Frame2D | Iterable[Iterable[int]]
    2) render_iter(display: DisplayInfo, cfg: dict) -> Iterator[Frame2D | Iterable[Iterable[int]]]
  where:
    - `t` is a monotonically increasing time since the worker started (seconds)
    - `display` has `width`, `height`, `fps` from the server’s `/config`
    - `cfg` is the latest per‑worker config dict from `/workers/:id/config`
  Return a Frame2D or a 2D iterable of integers 0/1. Default policy requires exact
  `height × width` dimensions; see Size Policy below.

Environment Variables
- `ORCH_URL`   : Base URL for orchestrator (default `http://localhost:8090`).
- `TARGET_URL` : Optional full POST URL to override destination. If set,
                 the harness posts RBM frames directly to this URL instead of
                 `/workers/:id/frame` on the orchestrator.
- `HEADLESS`   : When set to `1`, `true`, or `True`, disables the Tk preview.

Endpoints Used
- GET  `${ORCH_URL}/config`                    → discover canvas size and FPS
- GET  `${ORCH_URL}/workers/{id}/config`       → per‑worker runtime config (polled ~1 Hz)
- POST `${ORCH_URL}/workers/{id}/frame`        → RBM frames (unless `TARGET_URL` overrides)

Size Policy
- `strict` (default): frames must exactly match `display.height × display.width`.
  A mismatch raises a `ValueError` and the frame is not posted.
- `pad`: top‑left place the generated frame into a zeroed canvas and crop/pad
  to display bounds. Use for prototyping, but prefer strict for correctness.

Preview Behavior
- Attempts to create a Tk window via `workers.common.preview.make_preview`.
  If Tk is unavailable or `HEADLESS` is set, falls back to a no‑op preview.

Timing & Pacing
- The harness generates frames at a light background cadence (~60 Hz sleep), but
  the orchestrator re‑times the output toward the server’s FPS. Prefer using `t`
  (time‑based animation) for consistent motion regardless of pacing.
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


class WorkerBase(ABC):
    """
    Minimal harness for flip-disc workers.

    Subclass implements render(t, display, cfg) and the harness handles:
    - fetching display size/fps from orchestrator (/config)
    - polling worker config from orchestrator (/workers/:id/config)
    - local preview window (Tk when available; HEADLESS=1 disables)
    - RBM packaging and posting frames to orchestrator (/workers/:id/frame)

    Env vars:
    - ORCH_URL: orchestrator base URL (default http://localhost:8090)
    - TARGET_URL: override full post URL (bypasses orchestrator if desired)
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
    ) -> Union[Frame2D, Iterable[Iterable[int]]]:
        """Return a Frame2D or 2D 0/1 rows sized to the display (or smaller if size_policy allows)."""
        raise NotImplementedError

    # ---- Harness ----
    def _fetch_display(self, orch_url: str) -> DisplayInfo:
        """Fetch display config (canvas size, fps) from the orchestrator.

        Args:
        - orch_url: Base URL of the orchestrator (e.g., http://localhost:8090)

        Returns:
        - DisplayInfo with width, height, and fps.

        Raises:
        - RuntimeError if width/height are missing or invalid.
        """
        import urllib.request

        url = f"{orch_url}/config"
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        canvas = data.get("canvas") or {}
        width = int(canvas.get("width", 0))
        height = int(canvas.get("height", 0))
        fps = int(data.get("fps", 30) or 30)
        if width <= 0 or height <= 0:
            raise RuntimeError("invalid canvas dimensions from orchestrator /config")
        return DisplayInfo(width=width, height=height, fps=fps)

    def _fetch_worker_cfg(self, orch_url: str, timeout: float = 1.0) -> dict:
        """Poll the worker-specific config from the orchestrator.

        Args:
        - orch_url: Base URL of the orchestrator.
        - timeout: Request timeout in seconds.

        Returns:
        - A dict with the worker's live configuration, or {} if unreachable.
        """
        import urllib.request
        from urllib.error import URLError, HTTPError

        url = f"{orch_url}/workers/{self.worker_id}/config"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                payload = resp.read().decode("utf-8")
                try:
                    return json.loads(payload) if payload else {}
                except json.JSONDecodeError:
                    return {}
        except (URLError, HTTPError):
            # Orchestrator unreachable or returned an error; keep last known config
            return {}

    def _coerce_frame_shape(
        self, frame: Union[Frame2D, Iterable[Iterable[int]]], width: int, height: int
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

    def _post_frame(self, url: str, payload: bytes) -> None:
        """POST the encoded RBM payload to the given URL.

        Args:
        - url: Destination endpoint (orchestrator or server)
        - payload: RBM bytes (header + packed rows)
        """
        import urllib.request

        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/octet-stream")
        with urllib.request.urlopen(req, timeout=5) as resp:
            # Drain response (likely 204)
            _ = resp.read()

    def run(self) -> None:
        """Main worker loop.

        Behavior:
        - Discovers display size/fps from the orchestrator.
        - Optionally creates a local preview.
        - Polls worker config at ~1 Hz.
        - Generates frames via render() or render_iter().
        - Sends RBM frames to the orchestrator (or TARGET_URL override).

        This loop continues until interrupted (Ctrl+C) and is resilient to
        temporary network errors.
        """
        orch_url = os.environ.get("ORCH_URL", "http://localhost:8090")
        # Prefer posting to orchestrator; allow direct override
        default_target = f"{orch_url}/workers/{self.worker_id}/frame"
        target_url = os.environ.get("TARGET_URL", default_target)

        display = self._fetch_display(orch_url)
        preview = make_preview(
            display.width,
            display.height,
            scale=self.preview_scale,
            title=self.preview_title,
        )

        seq = 0
        last_cfg_poll = 0.0
        cfg: dict = {}
        start = time.monotonic()
        cfg_sig: Optional[str] = None
        frames_iter: Optional[Iterator[Union[Frame2D, Iterable[Iterable[int]]]]] = None

        # Optional generator path if subclass provides render_iter(display, cfg)
        render_iter_fn: Optional[
            Callable[
                [DisplayInfo, dict], Iterator[Union[Frame2D, Iterable[Iterable[int]]]]
            ]
        ] = None
        if hasattr(self, "render_iter"):
            # mypy/pylance-friendly getattr without type confusion
            render_iter_fn = getattr(self, "render_iter")  # type: ignore[assignment]

        try:
            while True:
                now = time.monotonic()
                # Poll worker config ~1 Hz
                if now - last_cfg_poll >= 1.0:
                    cfg = self._fetch_worker_cfg(orch_url)
                    last_cfg_poll = now
                    # Recreate generator if config changed
                    if render_iter_fn is not None:
                        new_sig = json.dumps(cfg, sort_keys=True)
                        if new_sig != cfg_sig:
                            frames_iter = render_iter_fn(display, cfg)
                            cfg_sig = new_sig

                if frames_iter is not None:
                    try:
                        frame_obj = next(frames_iter)
                    except StopIteration:
                        # Restart generator with current cfg
                        frames_iter = (
                            render_iter_fn(display, cfg) if render_iter_fn else None
                        )
                        frame_obj = self.render(now - start, display, cfg) if frames_iter is None else next(frames_iter)  # type: ignore[assignment]
                else:
                    frame_obj = self.render(now - start, display, cfg)
                frame2d = self._coerce_frame_shape(
                    frame_obj, display.width, display.height
                )

                # Local preview
                # Preview is best-effort; ignore UI errors
                try:
                    preview.update(frame2d)
                except Exception:
                    pass

                # RBM packaging + post
                from urllib.error import URLError, HTTPError

                try:
                    bits = pack_bitmap_1bit(frame2d, display.width, display.height)
                    payload = encode_rbm(
                        bits,
                        display.width,
                        display.height,
                        seq=seq,
                        frame_duration_ms=0,
                    )
                    self._post_frame(target_url, payload)
                except (URLError, HTTPError, TimeoutError):
                    # Orchestrator/server might be down; skip this tick
                    pass
                seq = (seq + 1) & 0xFFFFFFFF

                # Light pacing; orchestrator forwards at its own FPS
                time.sleep(1.0 / 60.0)
        except KeyboardInterrupt:
            try:
                preview.close()
            except Exception:
                pass
