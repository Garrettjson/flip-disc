import asyncio
import numpy as np
from src.driver import Driver
from src.display import Display
from src.controller import Controller
from src.animations.simplex_noise import SimplexNoise


#async def 


async def main():
    noise = SimplexNoise()

    disp = Display.from_shape(1, 4)
    with Driver(port="") as drv:
        c = Controller(drv, disp)

        c.play_animation(noise)
        

main()