import numpy as np
import matplotlib.pyplot as plt

class Panel:
    """
    TODO: comment
    """
    ROWS, COLS = 7, 28

    def __init__(
        self,
        address: bytes=bytes(1),
        rows: int=ROWS,
        cols: int=COLS,
        data: bytearray=bytearray(COLS)
    ):
        self.address = address
        self.rows = rows
        self.cols = cols
        self.shape = (rows, cols)
        self.data = data

    
    def _binary_list_to_int(self, l) -> int:
        """
        Converts a list of 1s & 0s into a integer.
        For example: [1, 0, 0, 1, 1, 0] --> 38
        """
        res = 0
        for elem in l:
            res = (res << 1) | elem
        return res


    def set_data(self, arr: np.ndarray) -> None:
        """
        TODO: comment
        """
        assert (
            self.shape == arr.shape
        ), f"panel shape must match array shape. panel: {self.shape}, array: {arr.shape}"

        vals = [self._binary_list_to_int(row) for row in arr.T]
        self.data = bytearray(vals)

    
    def show(self) -> None:
        """
        Visualizes data for the purpose of debugging. We need to convert the byte array back
        into a list of 1s and 0s (undo the `_binary_list_to_int` function) so that it can be
        displayed
        """
        arr = np.array([[int(b) for b in format(i, f"0{self.ROWS+1}b")] for i in self.data])
        plt.axis('off')
        plt.imshow(~arr.T, cmap='gray')
        plt.show()