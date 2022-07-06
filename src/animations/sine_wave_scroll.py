import numpy as np
from src.animations.animation import Animation
from src.frame import Frame
from typing import Iterator, Tuple

class SineWaveScroll(Animation):
    def __init__(
        self,
        period: float,
        amplitude: float,
        y_offset: int=0,
        x_offset: int=0,
        **kwargs
    ):
        """
        TODO: Comment
        """
        super().__init__(**kwargs)
        self.period = 2 * np.pi / period
        self.amplitude = amplitude
        self.x_offset = x_offset
        self.y_offset = y_offset + amplitude  # no negatives


    def next_frame(self) -> Iterator[Frame]:
        """
        TODO: Comment
        """
        BGRND, FRGND = 0, 1
        while True:
            arr = np.full(self.shape, BGRND)
            for row, col in self._calc_pts():
                arr[row][col] = FRGND
            yield Frame(arr)
            self.x_offset += 1
        

    def _calc_pts(self) -> Iterator[Tuple[int, int]]:
        """
        TODO: Comment
        """
        for x in range(self.rows):
            y = round(self.amplitude * np.sin(self.period * (x - self.x_offset)) + self.y_offset)
            # don't add point if its out of frame bounds
            if y < self.rows:
                yield (y, x)

