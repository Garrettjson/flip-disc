"""SPSC (Single-Producer/Single-Consumer) shared-memory ring buffers.

Provides a zero-copy ring buffer abstraction backed by a single contiguous
SharedMemory block, coordinated with two semaphores (free_slots/items) and
head/tail indices. Designed for one producer process and one consumer process.

Intended usage (producer side):
    idx, view = ring.producer_acquire()
    # write into view (numpy ndarray with shape)
    ring.producer_commit()

Consumer side:
    idx, view = ring.consumer_acquire()
    # read from view
    ring.consumer_release()

Notes:
- This implementation assumes strict SPSC semantics per ring; no locks are
  required for head/tail because only one process mutates each.
- Synchronization relies on semaphores to guarantee memory visibility order
  (producer writes, then signals items; consumer waits on items before read).
"""

from __future__ import annotations

import contextlib
import multiprocessing as mp
from dataclasses import dataclass
from multiprocessing.shared_memory import SharedMemory
from multiprocessing.sharedctypes import Synchronized
from multiprocessing.synchronize import Semaphore
from typing import TYPE_CHECKING, Literal

import numpy as np

DTypeStr = Literal["float32", "bool", "uint8"]


if TYPE_CHECKING:
    HeadIndex = Synchronized[int]
    TailIndex = Synchronized[int]
    CountSem = Semaphore
else:
    HeadIndex = Synchronized
    TailIndex = Synchronized
    CountSem = Semaphore


@dataclass(frozen=True)
class RingMeta:
    name: str
    capacity: int
    height: int
    width: int
    dtype: DTypeStr


class SPSCSharedRing:
    """Single-producer, single-consumer shared-memory ring of 2D frames."""

    def __init__(
        self,
        shm: SharedMemory,
        capacity: int,
        height: int,
        width: int,
        dtype: DTypeStr,
        head: HeadIndex,
        tail: TailIndex,
        free_slots: CountSem,
        items: CountSem,
    ) -> None:
        self._shm = shm
        self.capacity = int(capacity)
        self.height = int(height)
        self.width = int(width)
        self.dtype: DTypeStr = dtype
        self._head = head
        self._tail = tail
        self._free_slots = free_slots
        self._items = items

        np_dtype = np.dtype(self.dtype)
        self._slot_shape = (self.height, self.width)
        self._slot_nbytes = int(np_dtype.itemsize * self.height * self.width)
        expected_size = self.capacity * self._slot_nbytes
        # On some platforms (e.g., macOS), SharedMemory rounds up to page size.
        # Accept any size >= expected_size.
        if self._shm.size < expected_size:
            raise ValueError(
                f"SharedMemory too small: got {self._shm.size}, expected at least {expected_size}"
            )
        # Create a big view shaped as (capacity, H, W)
        self._buffer = np.ndarray(
            (self.capacity, *self._slot_shape), dtype=np_dtype, buffer=self._shm.buf
        )

    @classmethod
    def create(
        cls,
        capacity: int,
        height: int,
        width: int,
        dtype: DTypeStr,
        *,
        name: str | None = None,
    ) -> tuple[SPSCSharedRing, RingMeta, HeadIndex, TailIndex, CountSem, CountSem]:
        """Create a new ring and return it with the shared primitives.

        Returns the ring plus: (meta, head, tail, free_slots, items) which
        can be passed to child processes to attach to the same ring.
        """
        ctx = mp.get_context()
        np_dtype = np.dtype(dtype)
        slot_nbytes = int(np_dtype.itemsize * height * width)
        shm = SharedMemory(create=True, size=capacity * slot_nbytes, name=name)
        head = ctx.Value("i", 0)
        tail = ctx.Value("i", 0)
        free_slots = ctx.Semaphore(capacity)
        items = ctx.Semaphore(0)
        ring = cls(shm, capacity, height, width, dtype, head, tail, free_slots, items)
        meta = RingMeta(
            name=shm.name, capacity=capacity, height=height, width=width, dtype=dtype
        )
        return ring, meta, head, tail, free_slots, items

    @classmethod
    def attach(
        cls,
        meta: RingMeta,
        head: HeadIndex,
        tail: TailIndex,
        free_slots: CountSem,
        items: CountSem,
    ) -> SPSCSharedRing:
        """Attach to an existing ring using shared primitives passed by parent."""
        shm = SharedMemory(name=meta.name)
        return cls(
            shm,
            meta.capacity,
            meta.height,
            meta.width,
            meta.dtype,
            head,
            tail,
            free_slots,
            items,
        )

    # --- Life-cycle ------------------------------------------------------

    def close(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self._shm.close()

    def unlink(self) -> None:
        """Unlink underlying shared memory (call once in owner process)."""
        with contextlib.suppress(FileNotFoundError):
            self._shm.unlink()

    # --- Producer API ----------------------------------------------------

    def producer_acquire(self) -> tuple[int, np.ndarray]:
        """Reserve a free slot and return (index, writable view)."""
        self._free_slots.acquire()
        idx = int(self._head.value)
        self._head.value = (idx + 1) % self.capacity
        return idx, self._buffer[idx]

    def producer_commit(self) -> None:
        """Signal that a filled slot is ready for consumption."""
        self._items.release()

    # --- Consumer API ----------------------------------------------------

    def consumer_acquire(self) -> tuple[int, np.ndarray]:
        """Wait for an item and return (index, readable view)."""
        self._items.acquire()
        idx = int(self._tail.value)
        self._tail.value = (idx + 1) % self.capacity
        return idx, self._buffer[idx]

    def consumer_release(self) -> None:
        """Release the slot back to producer (after read)."""
        self._free_slots.release()

    def consumer_acquire_timeout(
        self, timeout: float
    ) -> tuple[int | None, np.ndarray | None]:
        """Try to acquire an item with timeout; returns (None, None) on timeout."""
        if self._items.acquire(timeout=timeout):
            idx = int(self._tail.value)
            self._tail.value = (idx + 1) % self.capacity
            return idx, self._buffer[idx]
        return None, None

    # --- Introspection ---------------------------------------------------

    @property
    def shape(self) -> tuple[int, int]:
        return self._slot_shape

    def get_status(self) -> dict:
        # Non-blocking estimates; semaphores may not expose current count portably
        return {
            "capacity": self.capacity,
            "slot_shape": self._slot_shape,
            "dtype": str(self.dtype),
        }
