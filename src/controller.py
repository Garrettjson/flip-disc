from src.display import Display
from src.driver import Driver
from src.frame import Frame
from src.animations.animation import Animation
from typing import List

class Controller:
    """
    TODO: comment
    """

    def __init__(self, driver: Driver, display: Display):
        self.driver = driver
        self.display = display

    
    async def _transmit_display(self) -> List[int]:
        return [await self.driver.transmit(panel) for panel in self.display.panels.flatten()]


    async def show_frame(self, frame: Frame) -> None:
        self.display.set_display(frame)
        await self._transmit_display()


    async def play_animation(self, anim: Animation) -> None:
        # TODO: keep a buffer of 1 seconds worth of frames
        # TODO: keep have some way to exist loop based on whats happening in main?
        while True:
            frm = next(anim)
            await self.show_frame(frm)