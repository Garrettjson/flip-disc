"""AnimationWorkerPool - manages animation worker processes and frame flow."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import multiprocessing as mp
import time
from queue import Empty
from typing import Any

from ..animations import list_animations
from ..config import DisplayConfig
from ..core.types import Frame
from ..workers.ipc import (
    Command,
    ConfigureCommand,
    CreditCommand,
    ResetCommand,
    Response,
    SetAnimationCommand,
    ShutdownCommand,
    TestPatternCommand,
)
from ..workers.runner import worker_main
from .display_pacer import DisplayPacer

logger = logging.getLogger(__name__)


class WorkerProcess:
    def __init__(self, worker_id: int, width: int, height: int):
        self.worker_id = worker_id
        self.width = width
        self.height = height

        self.rx_queue = mp.Queue()
        self.tx_queue = mp.Queue()

        self.process: mp.Process | None = None
        self.start_time = time.time()
        self.frames_generated = 0
        self.last_response_time = time.time()

        self.current_animation = "none"
        self.is_healthy = True

    def start(self) -> None:
        if self.process and self.process.is_alive():
            logger.warning(f"Worker {self.worker_id} already running")
            return

        self.process = mp.Process(
            target=worker_main,
            args=(
                self.width,
                self.height,
                self.worker_id,
                self.rx_queue,
                self.tx_queue,
            ),
            name=f"FlipDiscWorker-{self.worker_id}",
        )
        self.process.start()
        self.start_time = time.time()
        self.is_healthy = True
        logger.info(f"Started worker {self.worker_id} (PID: {self.process.pid})")

    def stop(self) -> None:
        if self.process and self.process.is_alive():
            try:
                self.rx_queue.put(ShutdownCommand(), timeout=1.0)
                self.process.join(timeout=3.0)
                if self.process.is_alive():
                    logger.warning(
                        f"Worker {self.worker_id} didn't exit cleanly, terminating"
                    )
                    self.process.terminate()
                    self.process.join(timeout=1.0)
                    if self.process.is_alive():
                        logger.error(
                            f"Worker {self.worker_id} didn't terminate, killing"
                        )
                        self.process.kill()
            except Exception as e:
                logger.error(f"Error stopping worker {self.worker_id}: {e}")
        self.process = None
        logger.info(f"Stopped worker {self.worker_id}")

    def send_command(self, command: Command) -> bool:
        if not self.process or not self.process.is_alive():
            self.is_healthy = False
            return False
        try:
            self.rx_queue.put(command, timeout=0.1)
            return True
        except Exception as e:
            logger.error(f"Failed to send command to worker {self.worker_id}: {e}")
            self.is_healthy = False
            return False

    def get_response(self, timeout: float = 0.1) -> Response | None:
        try:
            msg = self.tx_queue.get(timeout=timeout)
            if not isinstance(msg, Response):
                logger.error(
                    f"Worker {self.worker_id} sent unexpected message type: {type(msg)}"
                )
                return None
            response: Response = msg
            self.last_response_time = time.time()
            info = response.info or {}
            frames = info.get("frames_generated")
            if isinstance(frames, int):
                self.frames_generated = max(self.frames_generated, frames)
            return response
        except Empty:
            return None
        except Exception as e:
            logger.error(f"Error getting response from worker {self.worker_id}: {e}")
            return None

    def is_alive(self) -> bool:
        return self.process is not None and self.process.is_alive()

    def get_status(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "alive": self.is_alive(),
            "healthy": self.is_healthy,
            "current_animation": self.current_animation,
            "frames_generated": self.frames_generated,
            "uptime": time.time() - self.start_time,
            "last_response": time.time() - self.last_response_time,
        }


class AnimationWorkerPool:
    """Manages animation workers, credits, and frame collection."""

    def __init__(
        self, config: DisplayConfig, display_pacer: DisplayPacer, num_workers: int = 1
    ):
        self.config = config
        self.display_pacer: DisplayPacer = display_pacer
        self.num_workers = num_workers

        self.workers: list[WorkerProcess] = []
        self.current_worker_index = 0

        self.frame_collection_task: asyncio.Task | None = None
        self.running = False
        self.playing = False

        self.total_frames_collected = 0
        self.worker_errors = 0
        self.frames_dropped = 0

        for i in range(num_workers):
            self.workers.append(WorkerProcess(i, config.width, config.height))

        self.display_pacer.set_credit_callback(self._on_credits_available)
        self._seq = 0

    async def start(self) -> None:
        logger.info(f"Starting AnimationWorkerPool with {self.num_workers} workers")
        for worker in self.workers:
            worker.start()
        self.running = True
        self.frame_collection_task = asyncio.create_task(self._frame_collection_loop())
        logger.info("AnimationWorkerPool started (idle; not playing)")

    async def stop(self) -> None:
        logger.info("Stopping AnimationWorkerPool")
        self.running = False
        with contextlib.suppress(Exception):
            self.display_pacer.set_credit_callback(None)
        if self.frame_collection_task:
            self.frame_collection_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.frame_collection_task
        for worker in self.workers:
            worker.stop()
        logger.info("AnimationWorkerPool stopped")

    def _on_credits_available(self, count: int) -> None:
        if not self.running or not self.playing:
            return
        for _ in range(max(0, int(count))):
            worker = self.workers[self.current_worker_index]
            self.current_worker_index = (self.current_worker_index + 1) % len(
                self.workers
            )
            credit_cmd = CreditCommand()
            if not worker.send_command(credit_cmd):
                logger.warning(f"Failed to send credit to worker {worker.worker_id}")

    async def _frame_collection_loop(self) -> None:
        logger.info("Frame collection loop started")
        try:
            while self.running:
                frames_collected = 0
                for worker in self.workers:
                    if not worker.is_alive():
                        logger.warning(f"Worker {worker.worker_id} died, restarting")
                        await self._restart_worker(worker)
                        continue
                    response = worker.get_response(timeout=0.01)
                    if response:
                        if response.success and (response.frame is not None):
                            loop = asyncio.get_running_loop()
                            self._seq += 1
                            frame = Frame(
                                seq=self._seq,
                                produced_ts=loop.time(),
                                target_ts=None,
                                bits=response.frame,
                            )
                            success = await self.display_pacer.display_frame(frame)
                            if success:
                                self.total_frames_collected += 1
                                frames_collected += 1
                            else:
                                logger.warning("Hardware buffer full, frame dropped")
                                self.frames_dropped += 1
                        elif not response.success:
                            logger.error(
                                f"Worker {worker.worker_id} error: {response.error}"
                            )
                            self.worker_errors += 1
                await asyncio.sleep(0.001)
        except asyncio.CancelledError:
            logger.info("Frame collection loop cancelled")
        except Exception as e:
            logger.error(f"Frame collection error: {e}")

    async def _restart_worker(self, worker: WorkerProcess) -> None:
        logger.info(f"Restarting worker {worker.worker_id}")
        worker.stop()
        await asyncio.sleep(0.1)
        worker.start()
        if worker.current_animation != "none":
            await self._send_to_worker(
                worker, SetAnimationCommand(name=worker.current_animation)
            )

    async def _send_to_worker(self, worker: WorkerProcess, command: Command) -> bool:
        return worker.send_command(command)

    async def _send_to_all_workers(self, command: Command) -> None:
        for worker in self.workers:
            if worker.is_alive():
                worker.send_command(command)

    async def set_animation(
        self, name: str, params: dict[str, Any] | None = None
    ) -> None:
        if params is None:
            params = {}
        command = SetAnimationCommand(name=name, params=params)
        await self._send_to_all_workers(command)
        for worker in self.workers:
            worker.current_animation = name
        await self.play()
        logger.info(f"Set animation and started: {name}")

    async def configure_animation(self, params: dict[str, Any]) -> None:
        command = ConfigureCommand(params=params)
        await self._send_to_all_workers(command)
        logger.info(f"Configured current animation: {params}")

    async def reset_animation(self, seed: int | None = None) -> None:
        command = ResetCommand(seed=seed)
        await self._send_to_all_workers(command)
        logger.info(f"Reset animation (seed={seed})")

    async def display_test_pattern(self, pattern: str) -> None:
        command = TestPatternCommand(pattern=pattern)
        await self._send_to_all_workers(command)
        logger.info(f"Displaying test pattern: {pattern}")

    async def restart_workers(self) -> None:
        for worker in self.workers:
            await self._restart_worker(worker)
        logger.info("All workers restarted")

    async def play(self) -> None:
        if not self.playing:
            self.playing = True
            try:
                capacity = int(self.display_pacer.buffer.max_size)
                current = int(self.display_pacer.buffer.frames.qsize())
                credits_to_seed = max(0, capacity - current)
            except (AttributeError, TypeError, ValueError):
                credits_to_seed = self.num_workers
            if credits_to_seed > 0:
                self._on_credits_available(credits_to_seed)
            logger.info("Playback started (seeded credits=%s)", credits_to_seed)

    async def pause(self) -> None:
        if self.playing:
            self.playing = False
            logger.info("Playback paused")

    async def list_animations(self) -> list[str]:
        return list_animations()

    def get_status(self) -> dict[str, Any]:
        worker_stats = [worker.get_status() for worker in self.workers]
        alive_workers = sum(1 for w in self.workers if w.is_alive())
        healthy_workers = sum(1 for w in self.workers if w.is_healthy)
        return {
            "num_workers": self.num_workers,
            "alive_workers": alive_workers,
            "healthy_workers": healthy_workers,
            "playing": self.playing,
            "total_frames_collected": self.total_frames_collected,
            "frames_dropped": self.frames_dropped,
            "worker_errors": self.worker_errors,
            "workers": worker_stats,
        }
