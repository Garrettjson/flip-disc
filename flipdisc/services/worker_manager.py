"""WorkerManager - spawns and manages animation worker processes."""

import asyncio
import contextlib
import logging
import multiprocessing as mp
import time
from queue import Empty
from typing import Any

from ..anims import list_animations
from ..config import DisplayConfig
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

logger = logging.getLogger(__name__)


class WorkerProcess:
    """Container for a single worker process and its communication."""

    def __init__(self, worker_id: int, width: int, height: int):
        self.worker_id = worker_id
        self.width = width
        self.height = height

        # Communication queues
        self.rx_queue = mp.Queue()  # Commands to worker
        self.tx_queue = mp.Queue()  # Responses from worker

        # Process management
        self.process: mp.Process | None = None
        self.start_time = time.time()
        self.frames_generated = 0
        self.last_response_time = time.time()

        # State
        self.current_animation = "none"
        self.is_healthy = True

    def start(self):
        """Start the worker process."""
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

    def stop(self):
        """Stop the worker process."""
        if self.process and self.process.is_alive():
            try:
                # Send shutdown command
                shutdown_cmd = ShutdownCommand()
                self.rx_queue.put(shutdown_cmd, timeout=1.0)

                # Wait for process to exit
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
        """Send command to worker."""
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
        """Get Response dataclass (with optional frame) from worker."""
        try:
            msg = self.tx_queue.get(timeout=timeout)
            if not isinstance(msg, Response):
                logger.error(
                    f"Worker {self.worker_id} sent unexpected message type: {type(msg)}"
                )
                return None

            response: Response = msg
            self.last_response_time = time.time()

            if response.success and response.info:
                frames = response.info.get("frames_generated", 0)
                self.frames_generated = max(self.frames_generated, frames)

            return response
        except Empty:
            return None
        except Exception as e:
            logger.error(f"Error getting response from worker {self.worker_id}: {e}")
            return None

    def is_alive(self) -> bool:
        """Check if worker process is alive."""
        return self.process is not None and self.process.is_alive()

    def get_status(self) -> dict[str, Any]:
        """Get worker status."""
        return {
            "worker_id": self.worker_id,
            "alive": self.is_alive(),
            "healthy": self.is_healthy,
            "current_animation": self.current_animation,
            "frames_generated": self.frames_generated,
            "uptime": time.time() - self.start_time,
            "last_response": time.time() - self.last_response_time,
        }


class WorkerManager:
    """
    Manages a pool of animation worker processes.

    Handles:
    - Spawning/restarting workers
    - Load balancing credits across workers
    - Collecting frames and passing to HardwareTask
    - Worker health monitoring
    """

    def __init__(self, config: DisplayConfig, hardware_task, num_workers: int = 1):
        self.config = config
        self.hardware_task = hardware_task
        self.num_workers = num_workers

        # Worker processes
        self.workers: list[WorkerProcess] = []
        self.current_worker_index = 0  # For round-robin

        # Frame collection
        self.frame_collection_task: asyncio.Task | None = None
        self.running = False

        # Statistics
        self.total_frames_collected = 0
        self.worker_errors = 0

        # Initialize workers
        for i in range(num_workers):
            worker = WorkerProcess(i, config.width, config.height)
            self.workers.append(worker)

        # Set up credit callback
        hardware_task.set_credit_callback(self._on_credit_available)

    async def start(self):
        """Start all workers and frame collection."""
        logger.info(f"Starting WorkerManager with {self.num_workers} workers")

        # Start all worker processes
        for worker in self.workers:
            worker.start()

        # Start frame collection task
        self.running = True
        self.frame_collection_task = asyncio.create_task(self._frame_collection_loop())

        # Seed initial credits to fill the hardware buffer once at startup
        try:
            initial_credits = getattr(
                self.hardware_task.buffer, "max_size", self.num_workers
            )
            for _ in range(int(initial_credits)):
                self._on_credit_available()
            logger.info(f"Seeded {initial_credits} initial credits to workers")
        except Exception as e:
            logger.warning(f"Could not seed initial credits: {e}")

        logger.info("WorkerManager started")

    async def stop(self):
        """Stop all workers and frame collection."""
        logger.info("Stopping WorkerManager")
        self.running = False

        # Stop frame collection
        if self.frame_collection_task:
            self.frame_collection_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.frame_collection_task

        # Stop all workers
        for worker in self.workers:
            worker.stop()

        logger.info("WorkerManager stopped")

    def _on_credit_available(self):
        """Called by HardwareTask when a credit becomes available."""
        # Round-robin credit distribution
        worker = self.workers[self.current_worker_index]
        self.current_worker_index = (self.current_worker_index + 1) % len(self.workers)

        # Send credit command
        credit_cmd = CreditCommand()
        if not worker.send_command(credit_cmd):
            logger.warning(f"Failed to send credit to worker {worker.worker_id}")

    async def _frame_collection_loop(self):
        """Collect frames from workers and send to hardware."""
        logger.info("Frame collection loop started")

        try:
            while self.running:
                frames_collected = 0

                # Check all workers for responses
                for worker in self.workers:
                    if not worker.is_alive():
                        logger.warning(f"Worker {worker.worker_id} died, restarting")
                        await self._restart_worker(worker)
                        continue

                    response = worker.get_response(timeout=0.01)
                    if response:
                        if response.success and (response.frame is not None):
                            # Send frame to hardware
                            success = await self.hardware_task.display_frame(
                                response.frame
                            )
                            if success:
                                self.total_frames_collected += 1
                                frames_collected += 1
                            else:
                                logger.warning("Hardware buffer full, frame dropped")
                        elif not response.success:
                            logger.error(
                                f"Worker {worker.worker_id} error: {response.error}"
                            )
                            self.worker_errors += 1

                # Brief sleep to avoid busy waiting
                await asyncio.sleep(0.001)

        except asyncio.CancelledError:
            logger.info("Frame collection loop cancelled")
        except Exception as e:
            logger.error(f"Frame collection error: {e}")

    async def _restart_worker(self, worker: WorkerProcess):
        """Restart a failed worker."""
        logger.info(f"Restarting worker {worker.worker_id}")
        worker.stop()
        await asyncio.sleep(0.1)  # Brief delay
        worker.start()

        # Restore worker state
        if worker.current_animation != "none":
            await self._send_to_worker(
                worker, SetAnimationCommand(name=worker.current_animation)
            )

    async def _send_to_worker(self, worker: WorkerProcess, command: Command) -> bool:
        """Send command to specific worker."""
        return worker.send_command(command)

    async def _send_to_all_workers(self, command: Command):
        """Send command to all workers."""
        for worker in self.workers:
            if worker.is_alive():
                worker.send_command(command)

    async def set_animation(self, name: str, params: dict[str, Any] | None = None):
        """Set animation on all workers."""
        if params is None:
            params = {}

        command = SetAnimationCommand(name=name, params=params)
        await self._send_to_all_workers(command)

        # Update worker state
        for worker in self.workers:
            worker.current_animation = name

        logger.info(f"Set animation: {name}")

    async def configure_animation(self, name: str, params: dict[str, Any]):
        """Configure current animation."""
        command = ConfigureCommand(params=params)
        await self._send_to_all_workers(command)
        logger.info(f"Configured animation {name}: {params}")

    async def reset_animation(self, seed: int | None = None):
        """Reset current animation."""
        command = ResetCommand(seed=seed)
        await self._send_to_all_workers(command)
        logger.info(f"Reset animation (seed={seed})")

    async def display_test_pattern(self, pattern: str):
        """Display test pattern."""
        command = TestPatternCommand(pattern=pattern)
        await self._send_to_all_workers(command)
        logger.info(f"Displaying test pattern: {pattern}")

    async def restart_workers(self):
        """Restart all workers."""
        for worker in self.workers:
            await self._restart_worker(worker)
        logger.info("All workers restarted")

    async def list_animations(self) -> list[str]:
        """Get list of available animations."""
        return list_animations()

    def get_status(self) -> dict[str, Any]:
        """Get worker manager status."""
        worker_stats = [worker.get_status() for worker in self.workers]

        alive_workers = sum(1 for w in self.workers if w.is_alive())
        healthy_workers = sum(1 for w in self.workers if w.is_healthy)

        return {
            "num_workers": self.num_workers,
            "alive_workers": alive_workers,
            "healthy_workers": healthy_workers,
            "total_frames_collected": self.total_frames_collected,
            "worker_errors": self.worker_errors,
            "workers": worker_stats,
        }
