from src.display import Display
from src.driver import Driver
from src.frame import Frame
from src.animations.animation import Animation

class Controller:
    """
    TODO: comment
    """

    def __init__(self, driver: Driver, display: Display):
        self.driver = driver
        self.display = display

    
    def _transmit_display(self) -> None:  # maybe make this asyc or threaded?
        for panel in self.display.panels.flatten():
            self.driver.transmit(panel)


    def show_frame(self, frame: Frame) -> None:
        self.display.set_display(frame)
        self._transmit_display()


    def show_animation(self, anim: Animation) -> None:
        ...