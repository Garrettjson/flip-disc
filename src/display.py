from __future__ import annotations
import numpy as np
from panel import Panel
from frame import Frame
from typing import Any


class Display:
    """
    TODO: comment
    """
    def __init__(self, panels: np.ndarray):
        ROW_INDX, COL_INDX = 0, 1

        self.panels = panels
        self._x_panels = panels.shape[ROW_INDX]
        self._y_panels = panels.shape[COL_INDX]
        self._x_pixels = sum([p.shape[ROW_INDX] for p in panels[:, 0]])
        self._y_pixels = sum([p.shape[COL_INDX] for p in panels[0, :]])
        self._pixels = self._x_pixels * self._y_pixels
        

    @classmethod
    def from_shape(cls, x_panels: int, y_panels: int, **kwargs) -> Display:
        """
        Convience function for quick creation of display. Not recommended for use in production since
        panel displays and addresses are not explicitly set.
        Creates a display from a specified dimensionality of panels. For example, passing in 3,4 will
        result in a 12 panel display, with each row having 3 panels and each column having 4 panels.

        Args:
            - x_panels (int): number of panels in a single column
            - y_panels (int): number of panels in a single row
        """
        panels = np.array([Panel(i.to_bytes(1, "big"), **kwargs) for i in range(x_panels * y_panels)])
        return cls(panels.reshape(y_panels, x_panels))


    def set_display(self, frame: Frame) -> None:
        """
        TODO: comment
        """
        assert (
            frame.data.shape == (self._x_pixels, self._y_pixels)
        ), f"display and frame must be the same shape. display shape: {(self._x_pixels, self._y_pixels)}, frame shape: {frame.data.shape}"

        x = self._x_pixels // self._x_panels
        y = self._y_pixels // self._y_panels

        rshpd = np.reshape(frame.data, (self._x_panels, self._y_panels, x, y))
        for row in range(self._x_panels):
            for col in range(self._y_panels):
                self.panels[row][col].set_data(rshpd[row][col])
        
