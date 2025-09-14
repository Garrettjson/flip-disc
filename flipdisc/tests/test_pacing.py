import asyncio

from flipdisc.config import DisplayConfig
from flipdisc.engine.display_pacer import DisplayPacer
from flipdisc.engine.worker_pool import AnimationWorkerPool


async def _async_pacing_with_mock_serial():
    # Slow fps to make test deterministic(ish)
    cfg = DisplayConfig(refresh_rate=5.0, buffer_duration=0.4)
    hw = DisplayPacer(cfg)
    mgr = AnimationWorkerPool(cfg, display_pacer=hw, num_workers=1)

    hw_task = asyncio.create_task(hw.start())
    await mgr.start()
    await mgr.set_animation("bouncing_dot")

    await asyncio.sleep(2.0)

    status = mgr.get_status()
    frames = status["total_frames_collected"]
    # Expect roughly 10 frames at 5 fps over 2s; allow slack
    assert 6 <= frames <= 14

    await mgr.stop()
    await hw.stop()
    hw_task.cancel()


def test_pacing_with_mock_serial():
    asyncio.run(_async_pacing_with_mock_serial())
