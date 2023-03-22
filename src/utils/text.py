import cv2
import numpy as np
from typing import Dict


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
            for col in range(padding, img.shape[1]-1, letter_width + padding + margin):
                if i >= letters:
                    return
                char = chr(ascii_start + i)
                self[char] = Letter(
                    char=char,
                    data=img[row:row+letter_height, col:col+letter_width],
                    height=letter_height,
                    width=letter_width,
                )
                i += 1


class Text:
    def __init__(self, text: str, spacing: int = 1, alphabet: Alphabet = Alphabet()):
        total_letter_width = sum(alphabet[char].width for char in text)
        
        self.text = text
        self.data = np.full(
            (alphabet.letter_height, total_letter_width + (len(text) * spacing) - spacing),
            alphabet.bgrnd
        )

        offset = 0
        for char in text:
            letter = alphabet[char]
            self.data[:, offset:offset+letter.width] = letter.data
            offset += letter.width + spacing
        