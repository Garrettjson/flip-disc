import asyncio
from driver import Driver
from display import Display
from controller import Controller
from animations.simplex_noise import SimplexNoise


async def main():
    noise = SimplexNoise(scale=3, rows=14, cols=28)

    # disp = Display.from_shape(1, 2)
    # drv = Driver()
    # with Controller(drv, disp) as c:
    #     await c.play_animation(noise)

    from animations.n_body import NBody

    n = NBody.from_number(3, 1)
    noise.play()

    # from utils.text import TextBox
    # box = TextBox("Hello This Is", wrap=True)
    # print(box.data)


if __name__ == "__main__":
    asyncio.run(main())
