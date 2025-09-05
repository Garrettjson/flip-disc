from abc import ABC, abstractmethod
import yaml
from cv2 import repeat
from matplotlib import cm
import numpy as np
from frame import Frame
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from typing import Iterator


class Animation(ABC):
    """
    TODO: Comment
    """

    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
        FPS = config["display-fps"]
        x, y = config["display-shape"]
        rows, cols = config["panel-shape"]

    def __init__(self, fps: int = FPS, rows: int = rows * y, cols: int = cols * x):
        self.fps = fps
        self.rows = rows
        self.cols = cols
        self.shape = (rows, cols)
        self.nxtfrm = self.next_frame()

    def __next__(self) -> Frame:
        return next(self.nxtfrm)

    def __iter__(self) -> Iterator[Frame]:
        yield from self.nxtfrm

    @abstractmethod
    def next_frame(self) -> Iterator[Frame]: ...

    def play(self) -> None:
        """Convenience function for displaying animation on computer screen"""

        def animate(_):
            ax.clear()
            ax.imshow(~next(self).data, cmap="gray")

        fig, ax = plt.subplots(1, 1)
        _ = animation.FuncAnimation(fig, animate, frames=1000, blit=False, repeat=False)  # type: ignore
        plt.show()
