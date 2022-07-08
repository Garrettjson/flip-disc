import asyncio
import numpy as np
from driver import Driver
from display import Display
from controller import Controller
from animations.simplex_noise import SimplexNoise


async def main():
    noise = SimplexNoise()

    disp = Display.from_shape(1, 4)
    drv = Driver(port="/dev/cu.BeoplayH9-CSRGAIA")
    # with Controller(drv, disp) as c:
    #     ...
    #     #await c.play_animation(noise)
    c = Controller(drv, disp)
    await c.play_animation(noise)
        

asyncio.run(main())