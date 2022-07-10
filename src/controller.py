from __future__ import annotations
import asyncio
from display import Display
from driver import Driver
from frame import Frame
from animations.animation import Animation
from datetime import datetime
from typing import List

class Controller:
    """
    TODO: comment
    """
    MAX_FPS = 15
    MAX_FRAME_RATE_MS = (1/MAX_FPS) * 1e3

    def __init__(self, driver: Driver, display: Display):
        self.driver = driver
        self.display = display
        self.last_frame_at = datetime.now()
        

    def __enter__(self) -> Controller:
        self.driver.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, tb) -> None:
        self.driver.__exit__(exc_type, exc_value, tb)


    async def _transmit_display(self) -> List[bool]:
        # TODO: if all entries in the dict are true, return true else false
        return [await self.driver.transmit(panel) for panel in self.display.panels.flatten()]


    async def _populate_buffer(self, q: asyncio.Queue, anim: Animation):
        while True:
            frm = next(anim)
            await q.put(frm)


    async def _show_frames(self, q: asyncio.Queue):
        while True:
            frm = await q.get()
            await self.show_frame(frm)


    async def show_frame(self, frame: Frame) -> List[bool]:
        self.display.set_display(frame)

        # sleep so we don't exceed MAX_FPS
        elapsed_ms = (datetime.now() - self.last_frame_at).microseconds / 1e3
        if elapsed_ms <= self.MAX_FRAME_RATE_MS:
            t_ms = self.MAX_FRAME_RATE_MS - elapsed_ms
            await asyncio.sleep(t_ms / 1e3)

        res = await self._transmit_display()
        self.last_frame_at = datetime.now()
        return res


    async def play_animation(self, anim: Animation) -> None:
        # maintain a 1 second buffer of frames
        q = asyncio.Queue(maxsize=anim.fps)
        asyncio.create_task(self._show_frames(q))
        await self._populate_buffer(q, anim)
            
        

        