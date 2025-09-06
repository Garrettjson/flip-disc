from __future__ import annotations

from typing import Iterable, List

try:
    import tkinter as tk
except ImportError:  # pragma: no cover
    tk = None  # type: ignore


class TkGridViewer:
    """
    Minimal dependency-free viewer for small 1-bit frames using Tkinter.
    Draws each pixel as a square on a Canvas. Suitable for 28x14 scale-ups.
    """

    def __init__(
        self, width: int, height: int, scale: int = 20, title: str = "Flip-Disc Viewer"
    ):
        if tk is None:
            raise RuntimeError("tkinter is not available in this environment")
        self.width = width
        self.height = height
        self.scale = scale
        self.last_frame: List[List[int]] = [[0] * width for _ in range(height)]

        self.root = tk.Tk()
        self.root.title(title)
        w, h = width * scale, height * scale
        self.canvas = tk.Canvas(
            self.root, width=w, height=h, bg="#ffffff", highlightthickness=0
        )
        self.canvas.pack()

    def update(self, frame: Iterable[Iterable[int]]):
        s = self.scale
        for y, row in enumerate(frame):
            if y >= self.height:
                break
            for x, v in enumerate(row):
                if x >= self.width:
                    break
                v = 1 if v else 0
                if v == self.last_frame[y][x]:
                    continue
                self.last_frame[y][x] = v
                x0, y0 = x * s, y * s
                x1, y1 = x0 + s, y0 + s
                color = "#000000" if v else "#ffffff"
                self.canvas.create_rectangle(x0, y0, x1, y1, outline=color, fill=color)
        self.canvas.update()

