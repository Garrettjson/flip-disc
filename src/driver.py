from __future__ import annotations
import serial
from src.panel import Panel
from typing import Tuple, Dict


class Driver:
    """
    TODO: comment
    """

    def __init__(
        self,
        port: str="/dev/ttyUSB0",
        msg_bytes: int=28,
        instant_refresh: bool=True,
        speed: int=9600
    ):
        CFG_MAP: Dict[Tuple[int, bool], bytes] = {
            (0 , True ): bytes([0x82]),
            (28, True ): bytes([0x83]),
            (28, False): bytes([0x84]),
            (7 , True ): bytes([0x87]),
            (14, True ): bytes([0x92]),
            (14, False): bytes([0x93]),
        }
        self.port = port
        self.cfg = CFG_MAP[(msg_bytes, instant_refresh)]
        self.speed = speed
        self.connection = None

    
    def __enter__(self) -> Driver:
        self.connection = serial.Serial(self.port, self.speed).open()
        return self


    def __exit__(self, exc_type, exc_value, tb) -> None:
        self.connection.close()  # type: ignore

    
    def transmit(self, pnl: Panel) -> None:
        HEADER = bytes([0x80])
        EOT = bytes([0x8f])
        msg = HEADER + self.cfg + pnl.address + pnl.data + EOT
        self.connection.write(msg)  # type: ignore