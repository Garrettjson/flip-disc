from abc import ABC, abstractmethod
from src.frame import Frame
import matplotlib.pyplot as plt
from typing import Iterator

class Animation(ABC):
    """
    TODO: Comment
    """
    def __init__(self, frame_rate: int=15, rows: int=28, cols: int=28, **kwargs):
        self.frame_rate = frame_rate
        self.rows = rows
        self.cols = cols
        self.shape = (rows, cols)
        self.nxtfrm = self.next_frame()

    def __next__(self) -> Frame:
        return next(self.nxtfrm)

    def __iter__(self) -> Iterator[Frame]:
        yield from self.nxtfrm

    @abstractmethod
    def next_frame(self) -> Iterator[Frame]:
        ...

    def play(self) -> None:
        fig = plt.figure()
        