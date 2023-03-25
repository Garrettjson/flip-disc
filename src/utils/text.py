import cv2
import math
import yaml
import numpy as np
from typing import Dict, Union


class Letter:
    def __init__(self, char: str, data: np.ndarray, height: int, width: int):
        self.char = char
        self.data = data
        self.height = height
        self.width = width


class Alphabet(Dict[str, Letter]):
    """
    A dictionary of chars which map to Letter objects. This dictionary represents all
    of the letters in an alphabet. It is loaded in using a bitmap image containing the
    alphabet.

    Args:
        - charmap (str): the name of the bitmap image containing the alphabet
        - ascii_start (int): the ascii decimal code correspoding to the first letter in the
            bitmap alphabet
        - letters (int): number of letters in the bitmap alphabet we wish to read in
        - padding (int): amount of whitespace surrounding each letter
        - bgrnd (int): array value for background
        - fgrnd (int): array value for foreground
        - letter_width (int): the number of pixels across each letter in the bitmap alphabet is
        - letter_height (int): the number of pixels tall each letter in the bitmap alphabet is
    """

    def __init__(
        self,
        name: str = "standard.bmp",
        ascii_start: int = 32,  # " " (empty space)
        letters: int = 95,
        padding: int = 1,
        margin: int = 1,
        bgrnd: int = 0,
        fgrnd: int = 1,
        letter_width: int = 5,
        letter_height: int = 7,
    ):
        self.name = name
        self.bgrnd = bgrnd
        self.letter_width = letter_width
        self.letter_height = letter_height

        path = f"assets/text/{name}"
        img = cv2.imread(path, 0)  # read in greyscale
        img = np.where(img > 0, fgrnd, bgrnd)  # type: ignore

        i = 0
        for row in range(padding, img.shape[0], letter_height + padding + margin):
            for col in range(
                padding, img.shape[1] - 1, letter_width + padding + margin
            ):
                if i >= letters:
                    return
                char = chr(ascii_start + i)
                self[char] = Letter(
                    char=char,
                    data=img[row : row + letter_height, col : col + letter_width],
                    height=letter_height,
                    width=letter_width,
                )
                i += 1


class TextBox:
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
        x, y = config["display-shape"]
        rows, cols = config["panel-shape"]

    def __init__(
        self,
        text: str,
        letter_spacing: int = 1,
        line_spacing: int = 2,
        wrap: bool = False,
        box_width: Union[int, None] = None,
        alphabet: Alphabet = Alphabet(),
    ):
        total_letter_len = alphabet.letter_width * len(text)
        text_data_len = total_letter_len + (len(text) * letter_spacing) - letter_spacing

        self.text = text

        if wrap:
            box_width = box_width if box_width is not None else int(self.x * self.cols)
            letters_per_row = (box_width + letter_spacing) // (
                alphabet.letter_width + letter_spacing
            )
            box_rows = math.ceil(len(text) / letters_per_row)
            box_height = (
                box_rows * (alphabet.letter_height + line_spacing) - line_spacing
            )
        else:
            box_width = text_data_len
            box_height = alphabet.letter_height

        self._set_data(
            text, letter_spacing, line_spacing, box_width, box_height, alphabet
        )

    def _set_data(
        self,
        text: str,
        letter_spacing: int,
        line_spacing: int,
        box_width: int,
        box_height: int,
        alphabet: Alphabet,
    ):
        self.data = np.full((box_height, box_width), alphabet.bgrnd)

        x_offset, y_offset = 0, 0
        for char in text:
            letter = alphabet[char]
            if x_offset + letter.width > box_width:
                x_offset = 0
                y_offset += letter.height + line_spacing

            self.data[
                y_offset : y_offset + letter.height, x_offset : x_offset + letter.width
            ] = letter.data
            x_offset += letter.width + letter_spacing
