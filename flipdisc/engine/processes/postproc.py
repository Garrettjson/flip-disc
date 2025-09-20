"""Post-processor process entrypoint.

Consumes grayscale frames from the raw ring, applies dithering/threshold, and
publishes boolean frames to the ready ring.
"""

from __future__ import annotations

import time
from multiprocessing.sharedctypes import Synchronized
from multiprocessing.synchronize import Event, Semaphore

import numpy as np

from ...gfx.dither import ordered_bayer
from ..shared_ring import RingMeta, SPSCSharedRing


def postproc_main(
    raw_meta: RingMeta,
    raw_head: Synchronized[int],
    raw_tail: Synchronized[int],
    raw_free: Semaphore,
    raw_items: Semaphore,
    ready_meta: RingMeta,
    ready_head: Synchronized[int],
    ready_tail: Synchronized[int],
    ready_free: Semaphore,
    ready_items: Semaphore,
    running_event: Event,
) -> None:
    raw_ring = SPSCSharedRing.attach(raw_meta, raw_head, raw_tail, raw_free, raw_items)
    ready_ring = SPSCSharedRing.attach(
        ready_meta, ready_head, ready_tail, ready_free, ready_items
    )

    try:
        while True:
            if not running_event.is_set():
                time.sleep(0.005)
                continue

            # Block for next raw frame
            _, gray = raw_ring.consumer_acquire()

            # Dither to binary
            binary = ordered_bayer(gray)

            # Publish to ready ring
            _, out_view = ready_ring.producer_acquire()
            np.copyto(out_view, binary, casting="unsafe")
            ready_ring.producer_commit()

            # Release raw slot
            raw_ring.consumer_release()
    except KeyboardInterrupt:
        pass
    finally:
        raw_ring.close()
        ready_ring.close()
