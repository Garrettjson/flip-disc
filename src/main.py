import asyncio
from driver import Driver
from display import Display
from controller import Controller
from animations.simplex_noise import SimplexNoise


async def main():
    # noise = SimplexNoise(scale=3, rows=14, cols=28)

    # disp = Display.from_shape(1, 2)
    # drv = Driver()
    # with Controller(drv, disp) as c:
    #     await c.play_animation(noise)

    # from animations.n_body import NBody
    # n = NBody.from_number(3, 1)
    # n.play()

    # from utils.text import Alphabet
    # alpha = Alphabet("standard.bmp")
    import numpy as np
    print(np.full((5, 1), 0))
    
        

if __name__ == "__main__":
    asyncio.run(main())