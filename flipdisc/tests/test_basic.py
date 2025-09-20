#!/usr/bin/env python3
"""Basic assertions for the new architecture (no prints)."""

import asyncio

import numpy as np

from flipdisc.animations import get_animation, list_animations
from flipdisc.config import DisplayConfig
from flipdisc.engine.pipeline import DisplayPipeline


async def _async_test_pipeline_basic():
    config = DisplayConfig()
    pipeline = DisplayPipeline(config)
    await pipeline.start(animation="bouncing_dot")
    await pipeline.play()
    await asyncio.sleep(1.0)
    st = pipeline.get_status()
    assert st.running is True
    assert st.frames_presented > 0
    await pipeline.pause()
    await pipeline.stop()


async def _async_test_animations_direct():
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


async def _async_test_pipeline_integration():
    config = DisplayConfig()
    pipeline = DisplayPipeline(config)
    await pipeline.start(animation="bouncing_dot")
    await pipeline.play()
    await asyncio.sleep(1.0)
    st = pipeline.get_status()
    assert st.frames_presented > 0
    await pipeline.stop()


def test_pipeline_basic():
    asyncio.run(_async_test_pipeline_basic())


def test_animations_direct():
    asyncio.run(_async_test_animations_direct())


def test_pipeline_integration():
    asyncio.run(_async_test_pipeline_integration())
