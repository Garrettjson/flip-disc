#!/usr/bin/env python3
"""Animation worker process runner."""

import logging
import multiprocessing as mp
import sys
import time
from queue import Empty

import numpy as np

from ..animations import Animation, get_animation, list_animations
from ..core.exceptions import AnimationError
from ..gfx.dither import ordered_bayer
from .ipc import (
    Command,
    ConfigureCommand,
    CreditCommand,
    ResetCommand,
    Response,
    SetAnimationCommand,
    ShutdownCommand,
    TestPatternCommand,
)


class Worker:
    """
    Animation worker process.

    Runs in separate process and generates frames on demand.
    Communicates via multiprocessing queues using the IPC protocol.
    """

    def __init__(self, width: int, height: int, worker_id: int = 0):
        self.width = width
        self.height = height
        self.worker_id = worker_id

        self.current_animation: Animation | None = None
        self.dt = 1 / 60  # Target 60fps for smooth animation

        # Statistics
        self.frames_generated = 0
        self.start_time = time.time()

        # Setup logging for this worker
        logging.basicConfig(
            level=logging.INFO,
            format=f"[Worker-{worker_id}] %(levelname)s: %(message)s",
        )
        self.logger = logging.getLogger(f"worker-{worker_id}")

    def run(self, rx_queue: mp.Queue, tx_queue: mp.Queue):
        """Main worker loop."""
        self.logger.info(f"Worker started: {self.width}x{self.height}")

        try:
            while True:
                try:
                    # Get command from main process
                    command = rx_queue.get(timeout=1.0)

                    # Process command
                    response = self._process_command(command)

                    # Send response back directly
                    if response:
                        tx_queue.put(response)

                except Empty:
                    # Periodic heartbeat/cleanup
                    continue
                except Exception as e:
                    self.logger.error(f"Error processing command: {e}")
                    error_response = Response(success=False, error=str(e))
                    tx_queue.put(error_response)

        except KeyboardInterrupt:
            self.logger.info("Worker interrupted")
        except Exception as e:
            self.logger.error(f"Worker fatal error: {e}")
        finally:
            self.logger.info(
                f"Worker shutting down (generated {self.frames_generated} frames)"
            )

    def _process_command(self, command: Command) -> Response | None:  # noqa: PLR0911
        """Process a single command."""
        try:
            if isinstance(command, CreditCommand):
                return self._handle_credit()
            if isinstance(command, SetAnimationCommand):
                return self._handle_set_animation(command)
            if isinstance(command, ResetCommand):
                return self._handle_reset(command)
            if isinstance(command, ConfigureCommand):
                return self._handle_configure(command)
            if isinstance(command, TestPatternCommand):
                return self._handle_test_pattern(command)
            if isinstance(command, ShutdownCommand):
                self.logger.info("Shutdown command received")
                sys.exit(0)
            else:
                return Response(success=False, error=f"Unknown command: {command.cmd}")

        except Exception as e:
            self.logger.error(f"Command processing error: {e}")
            return Response(success=False, error=str(e))

    def _handle_credit(self) -> Response:
        """Generate a frame in response to credit."""
        if not self.current_animation:
            return Response(success=False, error="No animation loaded")

        try:
            # Step animation
            self.current_animation.step(self.dt)

            # Render to grayscale
            gray_frame = self.current_animation.render_gray()

            # Dither to binary (bool array)
            binary_frame = ordered_bayer(gray_frame)

            self.frames_generated += 1

            return Response(
                success=True,
                frame=binary_frame,
                info={
                    "frames_generated": self.frames_generated,
                    "produced_ts": time.time(),
                    "animation": self.current_animation.get_info(),
                },
            )

        except Exception as e:
            self.logger.error(f"Frame generation failed: {e}")
            return Response(success=False, error=f"Frame generation failed: {e}")

    def _handle_set_animation(self, command: SetAnimationCommand) -> Response:
        """Set current animation."""
        try:
            self.current_animation = get_animation(
                command.name, self.width, self.height
            )
            if command.params:
                self.current_animation.configure(**command.params)

            self.logger.info(f"Animation set: {command.name}")
            return Response(
                success=True,
                info={
                    "animation": command.name,
                    "params": command.params,
                    "available": list_animations(),
                },
            )

        except AnimationError as e:
            return Response(success=False, error=str(e))

    def _handle_reset(self, command: ResetCommand) -> Response:
        """Reset current animation."""
        if not self.current_animation:
            return Response(success=False, error="No animation loaded")

        try:
            self.current_animation.reset(command.seed)
            self.logger.info(f"Animation reset (seed={command.seed})")
            return Response(success=True, info={"seed": command.seed})
        except Exception as e:
            return Response(success=False, error=str(e))

    def _handle_configure(self, command: ConfigureCommand) -> Response:
        """Configure current animation."""
        if not self.current_animation:
            return Response(success=False, error="No animation loaded")

        try:
            self.current_animation.configure(**command.params)
            self.logger.info(f"Animation configured: {command.params}")
            return Response(success=True, info={"params": command.params})
        except Exception as e:
            return Response(success=False, error=str(e))

    def _handle_test_pattern(self, command: TestPatternCommand) -> Response:
        """Generate a test pattern."""
        try:
            # Create test pattern directly
            frame = np.zeros((self.height, self.width), dtype=np.float32)

            if command.pattern == "checkerboard":
                for y in range(self.height):
                    for x in range(self.width):
                        frame[y, x] = (x + y) % 2
            elif command.pattern == "solid":
                frame[:, :] = 1.0
            # "clear" pattern is already all zeros

            # Convert to binary boolean image
            binary_frame = frame > 0.5

            return Response(
                success=True, frame=binary_frame, info={"pattern": command.pattern}
            )

        except Exception as e:
            return Response(success=False, error=str(e))


def worker_main(
    width: int, height: int, worker_id: int, rx_queue: mp.Queue, tx_queue: mp.Queue
):
    """Entry point for worker process."""
    worker = Worker(width, height, worker_id)
    worker.run(rx_queue, tx_queue)


if __name__ == "__main__":
    # For testing worker in standalone mode
    import argparse

    parser = argparse.ArgumentParser(description="Animation worker process")
    parser.add_argument("--width", type=int, default=112, help="Display width")
    parser.add_argument("--height", type=int, default=56, help="Display height")
    parser.add_argument("--worker-id", type=int, default=0, help="Worker ID")
    args = parser.parse_args()

    # Create dummy queues for testing
    rx_queue = mp.Queue()
    tx_queue = mp.Queue()

    logging.basicConfig(level=logging.INFO)
    logging.getLogger(__name__).info(
        "Starting worker %s (%sx%s)", args.worker_id, args.width, args.height
    )
    worker_main(args.width, args.height, args.worker_id, rx_queue, tx_queue)
