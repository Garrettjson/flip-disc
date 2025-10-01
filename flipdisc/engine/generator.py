"""Unified generator process for all animations."""

from __future__ import annotations

import time
from multiprocessing.sharedctypes import Synchronized
from multiprocessing.synchronize import Event, Semaphore
from typing import Any

import numpy as np

from ..animations import get_animation
from ..gfx.postprocessing import apply_processing_pipeline
from .shared_ring import RingMeta, SPSCSharedRing


def unified_generator(
    ready_meta: RingMeta,
    ready_head: Synchronized[int],
    ready_tail: Synchronized[int],
    ready_free_slots: Semaphore,
    ready_items: Semaphore,
    running_event: Event,
    reset_event: Event,
    width: int,
    height: int,
    animation: str,
    params: dict[str, Any],
) -> None:
    """Unified generator that handles all animation types with processing pipelines."""
    ready_ring = SPSCSharedRing.attach(
        ready_meta, ready_head, ready_tail, ready_free_slots, ready_items
    )

    anim = get_animation(animation, width, height)
    if params:
        anim.configure(**params)

    dt = 1.0 / 60.0

    try:
        while True:
            if not running_event.is_set():
                time.sleep(0.01)
                if reset_event.is_set():
                    reset_event.clear()
                    anim.reset()
                continue

            if reset_event.is_set():
                reset_event.clear()
                anim.reset()

            anim.step(dt)
            gray_frame = anim.render_gray()

            # Apply processing pipeline
            processed_frame = apply_processing_pipeline(
                gray_frame, anim.processing_steps
            )

            _, view = ready_ring.producer_acquire()
            np.copyto(view, processed_frame, casting="unsafe")
            ready_ring.producer_commit()
    except KeyboardInterrupt:
        pass
    finally:
        ready_ring.close()
