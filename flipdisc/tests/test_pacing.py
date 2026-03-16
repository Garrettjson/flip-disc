import asyncio

from flipdisc.config import DisplayConfig
from flipdisc.engine.pipeline import DisplayPipeline


async def _async_pacing_with_mock_serial():
    # Slow fps to make test deterministic(ish)
    cfg = DisplayConfig(refresh_rate=5.0, buffer_duration=0.4)
    pipeline = DisplayPipeline(cfg)
    await pipeline.start(animation="bouncing_dot")
    await pipeline.play()

    await asyncio.sleep(3.0)

    status = pipeline.get_status()
    frames = status.frames_presented
    # Expect roughly 15 frames at 5 fps over 3s; allow generous slack for process startup
    assert 5 <= frames <= 20

    await pipeline.stop()


def test_pacing_with_mock_serial():
    asyncio.run(_async_pacing_with_mock_serial())
