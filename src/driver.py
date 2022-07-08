from __future__ import annotations
from aioserial import AioSerial
from panel import Panel
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


    
    def __enter__(self) -> Driver:
        self.connection: AioSerial = AioSerial(self.port, self.speed).open()  # type: ignore
        return self


    def __exit__(self, exc_type, exc_value, tb) -> None:
        self.connection.close()

    
    async def transmit(self, pnl: Panel) -> int:  # TODO: make sure this is actually async, could make this ansync.to_thread() if not
        """
        Asynchronously makes serial write calls to the flip disc display over the rs485 protocol.
        Since serial operations are comparatively slow, making this non-blocking code frees up CPU time.

        TODO: comment
        """
        HEADER = bytes([0x80])
        EOT = bytes([0x8f])
        msg = HEADER + self.cfg + pnl.address + pnl.data + EOT
        # TODO: I think write returns the length of the message written, if it does, we should check that the length of the message
        #       written is the same as the length of the message sent, we should return the boolean expression of that check
        return await self.connection.write_async(msg)
