"""Generator process entrypoint.

Consumes control events/config and produces grayscale frames into the raw ring.
"""

from __future__ import annotations

import multiprocessing as mp
import time

import numpy as np

from ...animations import get_animation
from ..shared_ring import RingMeta, SPSCSharedRing


def generator_main(
    raw_meta: RingMeta,
    head,  # mp.Value
    tail,  # mp.Value
    free_slots,  # mp.Semaphore
    items,  # mp.Semaphore
    running_event: mp.Event,
    reload_event: mp.Event,
    reset_event: mp.Event,
    width: int,
    height: int,
    animation: str,
    params: dict,
) -> None:
    ring = SPSCSharedRing.attach(raw_meta, head, tail, free_slots, items)
    anim = get_animation(animation, width, height)
    if params:
        anim.configure(**params)

    # Target animation step rate; presenter paces output via consumer queue
    dt = 1.0 / 60.0

    try:
        while True:
            if not running_event.is_set():
                time.sleep(0.01)
                # Check for reload while idle
                if reload_event.is_set():
                    reload_event.clear()
                    # For now, ignore reload; a higher-level controller would restart the process with new params
                if reset_event.is_set():
                    reset_event.clear()
                    anim.reset()
                continue

            # Handle control flags
            if reload_event.is_set():
                reload_event.clear()
                # No-op placeholder for future dynamic reconfig
            if reset_event.is_set():
                reset_event.clear()
                anim.reset()

            # Produce next gray frame into ring
            anim.step(dt)
            gray = anim.render_gray()
            _, view = ring.producer_acquire()
            # Write into shared slot (ensure dtype/shape)
            np.copyto(view, gray, casting="unsafe")
            ring.producer_commit()
    except KeyboardInterrupt:
        pass
    finally:
        ring.close()
