import numpy as np
from opensimplex import noise3array
from animations.animation import Animation
from frame import Frame
from typing import Iterator


class SimplexNoise(Animation):
    def __init__(
        self, scale: int = 4, step_size: float = 0.05, bw_threshold: int = 150, **kwargs
    ):
        """
        TODO: Comment
        """
        super().__init__(**kwargs)
        self.scale = scale
        self.step_size = step_size
        self.bw_threshold = bw_threshold

    def next_frame(self) -> Iterator[Frame]:
        """
        TODO: Comment
        """
        i = 0
        y = np.arange(self.rows)
        x = np.arange(self.cols)

        while True:
            arr = noise3array(x / self.scale, y / self.scale, np.array([i]))[0, :, :]
            clrd = (arr + 1) * self.bw_threshold
            yield Frame.from_array(clrd)
            i += self.step_size
