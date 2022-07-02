from __future__ import annotations
import cv2
import numpy as np
import matplotlib.pyplot as plt
from warnings import warn
from typing import Union, Tuple
from scipy.ndimage import rotate


class Frame:
    """
    A Frame is an array representation of an image stored as an array of 1s & 0s,
    corresponding to the two states of a fip-disc display. A Frame must be the same
    size as the display (aka. the SHAPE) in order to facilitate easier combining and
    displaying of Frames. Multiple Frames can be combined (added & subtracted) in order
    to create complex images.

    A Frame can be initialized via:
        - A 2d numpy array of size SHAPE (using constructor)
        - A 2d numpy array (using from array_method)
        - An image (using the from_image method)

    In order to fulfill the requirement of a frame being of size SHAPE, the Frame class
    allows for image/array resizing, padding, and shifting.

    Args:
        - data (np.ndarray): A 2d numpy array of size SHAPE
    """

    BGRND = 0
    FRGND = 1
    BW_THRESHOLD = 165
    SHAPE = (28, 28)

    def __init__(self, data: np.ndarray=np.full(SHAPE, BGRND)):
        self.data = data.astype(int)

    def __add__(self, img: Frame) -> Frame:
        return Frame(self.data | img.data)

    def __sub__(self, img: Frame) -> Frame:
        return Frame(self.data ^ (self.data & img.data))

    def clear(self) -> None:
        self.data.fill(self.BGRND)

    def shift(self, x_units: int, y_units: int) -> Frame:
        data = self.data
        data = np.roll(data, x_units, 1)  # x
        data = np.roll(data, y_units, 0)  # y
        return Frame(data)

    def flip(self, axis: str) -> Frame:
        axs_map = {'x': 1, 'y': 0}
        data = np.flip(self.data, axs_map[axis])
        return Frame(data)

    def rotate(self, angle: Union[int, float]) -> Frame:
        data = rotate(self.data, angle)
        return Frame(data)

    @classmethod
    def _resize(cls, img: np.ndarray, shape: Tuple[int, int]=SHAPE) -> np.ndarray:
        return cv2.resize(img, shape)


    @classmethod
    def _binarize_values(
        cls,
        img: np.ndarray,
        threshold: int=BW_THRESHOLD,
        foreground: int=FRGND,
        background: int=BGRND,
    ) -> np.ndarray:
        """
        TODO: comment
        """
        return np.where(img < threshold, foreground, background)


    @classmethod
    def _pad_frame(
        cls,
        img: np.ndarray,
        value: int=255,  # white
        base_coord: Tuple[int, int]=(0,0),  # (x,y)
    ) -> np.ndarray:
        """
        Increases the size of the Frame to be of size SHAPE by padding the Frame with a single
        value.

        Args:
            - img (np.ndarray): an array representing an image
            - value (int): the value with which the padding area will be filled with. Note that
                since all image are converted to 1s & 0s (b&w) after this procedure, a fill value
                of 255 represents white and a fill value of 0 represents black.
            - base_coord (Tuple[int, int]): the location relative to the total size of the Frame
                that the image will "start". This coordinate corresponds to the upper left-hand
                corner of the image
        """

        img_y, img_x = img.shape  # (rows, cols)
        coord_x, coord_y = base_coord
        SHAPE_Y, SHAPE_X = cls.SHAPE

        left_pad = coord_x
        right_pad = SHAPE_X - (coord_x + img_x)
        top_pad = coord_y
        bottom_pad = SHAPE_Y - (coord_y + img_y)

        assert (
            right_pad >= 0
        ), f"image width + base_coord x ({coord_x + img_x}) is greater than frame width ({SHAPE_X})"
        assert (
            bottom_pad >= 0
        ), f"image height + base_coord y ({coord_y + img_y}) is greater than frame height ({SHAPE_Y})"
        
        return np.pad(
            img, ((top_pad, bottom_pad), (left_pad, right_pad)), constant_values=value  # type: ignore
        )


    @classmethod
    def _process_data(
        cls,
        img: np.ndarray,
        scaling: str="resize",
        base_coord: Tuple[int, int]=(0,0),  # (x,y)
    ) -> np.ndarray:
        """
        TODO: fix comment
        
        Args:
            - name (str): the name of the file containing the image
            - path (str): the path to the folder where the image is located
            - scaling (str): Can be either "resize" or "pad". Resize shrinks or enlarges the images to
                be of size SHAPE, while pad surrounds the image with a given value/color to to be of
                size shape
            - base_coord (Tuple[int, int]): sets the "start" of the image in the case of scaling via the
                "pad" option. This corresponds to the upper left-hand corner of the image. base_coord is
                ignored if scaling via the "resize" option
        """

        scalings = ["resize", "pad"]
        assert scaling in scalings, f"scaling must be one of: {scalings}"

        if scaling == "resize" and base_coord != (0,0):
            warn("if scaling == 'resize' then base_coord will be ignored")

        if scaling == "resize" and img.shape != cls.SHAPE:
            img = Frame._resize(img, cls.SHAPE)
            
        elif scaling == "pad":
            img = Frame._pad_frame(img=img, base_coord=base_coord)

        return Frame._binarize_values(img)


    @classmethod
    def from_array(
        cls,
        img: np.ndarray,
        scaling: str="resize",
        base_coord: Tuple[int, int]=(0,0),  # (x,y))
    ) -> Frame:
        """
        TODO: comment
        """
        
        data = Frame._process_data(img, scaling, base_coord)
        return cls(data)


    @classmethod
    def from_image(
        cls,
        name: str,
        path: str="",
        scaling: str="resize",
        base_coord: Tuple[int, int]=(0,0),  # (x,y)
    ) -> Frame:
        """
        TODO: comment
        """

        img = cv2.imread(path + name, 0)  # read in greyscale
        data = Frame._process_data(img, scaling, base_coord)
        return cls(data)


    def show(self) -> None:
        plt.axis('off')
        plt.imshow(~self.data, cmap='gray')
        plt.show()