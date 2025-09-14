#!/usr/bin/env python3
"""Basic assertions for the new architecture (no prints)."""

import asyncio

import numpy as np

from flipdisc.anims import get_animation, list_animations
from flipdisc.config import DisplayConfig
from flipdisc.services.hardware import HardwareTask
from flipdisc.services.worker_manager import WorkerManager


def create_test_pattern(
    width: int, height: int, pattern: str = "checkerboard"
) -> np.ndarray:
    pixels = np.zeros((height, width), dtype=bool)
    if pattern == "checkerboard":
        for y in range(height):
            for x in range(width):
                pixels[y, x] = (x + y) % 2 == 0
    elif pattern == "border":
        if height > 1:
            pixels[0, :] = True
            pixels[-1, :] = True
        if width > 1:
            pixels[:, 0] = True
            pixels[:, -1] = True
    elif pattern == "solid":
        pixels[:, :] = True
    # "clear" leaves pixels all False
    return pixels


async def test_hardware_basic():
    config = DisplayConfig()
    hardware = HardwareTask(config)

    hw_task = asyncio.create_task(hardware.start())
    await asyncio.sleep(0.1)

    status = hardware.get_status()
    assert status["running"] is True
    assert status["connected"] is True

    for pattern in ["checkerboard", "border", "solid", "clear"]:
        frame_bits = create_test_pattern(config.width, config.height, pattern)
        assert frame_bits.shape == (config.height, config.width)
        assert frame_bits.dtype == bool
        success = await hardware.display_frame(frame_bits)
        assert success is True
        await asyncio.sleep(0.1)

    await hardware.stop()
    hw_task.cancel()
    # No prints; rely on assertions


async def test_anims_direct():
    config = DisplayConfig(width=28, height=14)
    names = list_animations()
    assert len(names) > 0
    for name in names:
        anim = get_animation(name, config.width, config.height)
        for _ in range(3):
            anim.step(1 / 30)
            gray = anim.render_gray()
            assert gray.shape == (config.height, config.width)
            assert gray.ndim == 2
            assert gray.dtype in (np.float32, np.float64)
            assert np.isfinite(gray).all()
            assert gray.min() >= 0.0 and gray.max() <= 1.0
            await asyncio.sleep(0.05)
    # No prints


async def test_worker_integration():
    config = DisplayConfig()
    hardware = HardwareTask(config)
    manager = WorkerManager(config, hardware_task=hardware, num_workers=1)

    hw_task = asyncio.create_task(hardware.start())
    await manager.start()
    await manager.set_animation("bouncing_dot")

    await asyncio.sleep(1.0)
    mstat = manager.get_status()
    assert mstat["alive_workers"] == 1
    assert mstat["healthy_workers"] == 1
    assert mstat["total_frames_collected"] > 0

    await manager.stop()
    await hardware.stop()
    hw_task.cancel()
    # No prints


async def main():
    await test_hardware_basic()
    await test_anims_direct()
    await test_worker_integration()
    # No prints


if __name__ == "__main__":
    asyncio.run(main())
