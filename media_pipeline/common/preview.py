from __future__ import annotations

import os
from typing import Iterable, Optional

try:
    from .viewer import TkGridViewer  # Tkinter-based
except Exception:  # pragma: no cover
    TkGridViewer = None  # type: ignore


class _NoOpPreview:
    def __init__(self, *_, **__):
        pass

    def update(self, _frame: Iterable[Iterable[int]]):
        return None

    def close(self):  # for symmetry
        return None


class _TkPreview:
    def __init__(
        self, width: int, height: int, scale: int = 20, title: str = "Preview"
    ):
        if TkGridViewer is None:
            raise RuntimeError("Tkinter preview unavailable")
        self._viewer = TkGridViewer(width, height, scale=scale, title=title)

    def update(self, frame: Iterable[Iterable[int]]):
        self._viewer.update(frame)

    def close(self):
        # Tk viewer closes via window manager; nothing special needed
        return None


def make_preview(
    width: int, height: int, *, scale: int = 20, title: str = "Worker Preview"
):
    """
    Create a preview object with a uniform API:
    - update(frame): display the given 2D 0/1 iterable
    - close(): optional cleanup

    Behavior:
    - If env `HEADLESS=1` or Tkinter is not available, returns a no-op preview.
    - Otherwise returns a Tk-based preview window.
    """
    headless = os.environ.get("HEADLESS", "0") in ("1", "true", "True")
    if headless or TkGridViewer is None:
        return _NoOpPreview()
    try:
        return _TkPreview(width, height, scale=scale, title=title)
    except Exception:
        # Fallback to no-op if Tk initialization fails
        return _NoOpPreview()

