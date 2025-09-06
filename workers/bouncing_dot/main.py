from __future__ import annotations

from typing import Iterable, List

from workers.common.base import WorkerBase, DisplayInfo, Frame2D


class BouncingDot(WorkerBase):
    """Simple bouncing pixel demo using the WorkerBase harness.

    Maintains internal (x, y) and direction state, and returns a full
    frame each call; the harness handles pacing and posting.
    """

    def __init__(self) -> None:
        super().__init__(
            "bouncing-dot",
            size_policy="strict",
            preview_scale=20,
            preview_title="Worker Local Preview",
        )
        self.x = 0
        self.y = 0
        self.dx = 1
        self.dy = 1

    def render(self, t: float, display: DisplayInfo, cfg: dict) -> Frame2D:
        """Render a single frame at time t.

        Args:
        - t: seconds since worker started (monotonic)
        - display: DisplayInfo with canvas dimensions
        - cfg: worker config dict (unused here)
        """
        w, h = display.width, display.height
        # Initialize inside bounds in case size changed
        self.x = max(0, min(self.x, w - 1))
        self.y = max(0, min(self.y, h - 1))

        fr = Frame2D.zeros(h, w)
        fr.data[self.y][self.x] = 1

        # Step for next frame
        self.x += self.dx
        self.y += self.dy
        if self.x <= 0 or self.x >= w - 1:
            self.dx *= -1
            self.x = max(0, min(self.x, w - 1))
        if self.y <= 0 or self.y >= h - 1:
            self.dy *= -1
            self.y = max(0, min(self.y, h - 1))

        return fr


def main() -> None:
    BouncingDot().run()


if __name__ == "__main__":
    main()
