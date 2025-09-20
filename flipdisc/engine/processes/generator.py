"""Generator process entrypoint.

Consumes control events/config and produces grayscale frames into the raw ring.
"""

from __future__ import annotations

import time
from multiprocessing.sharedctypes import Synchronized
from multiprocessing.synchronize import Event, Semaphore
from typing import Any

import numpy as np

from ...animations import get_animation
from ..shared_ring import RingMeta, SPSCSharedRing


def generator_main(
    raw_meta: RingMeta,
    head: Synchronized[int],
    tail: Synchronized[int],
    free_slots: Semaphore,
    items: Semaphore,
    running_event: Event,
    reset_event: Event,
    width: int,
    height: int,
    animation: str,
    params: dict[str, Any],
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
                # Check for reset while idle
                if reset_event.is_set():
                    reset_event.clear()
                    anim.reset()
                continue

            # Handle control flags
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
