#!/usr/bin/env python3
"""
Main application entry point.

Wires together DisplayPipeline (generator → postproc → presenter) and ApiServer.
"""

import argparse
import asyncio
import logging
import multiprocessing as mp
import signal
import sys

from .config import load_config
from .engine.api_server import ApiServer
from .engine.pipeline import DisplayPipeline
from .logging_conf import setup_logging


class FlipDiscApplication:
    """Main application orchestrator."""

    def __init__(self):
        self.config = None
        self.hardware_task = None
        self.worker_manager = None
        self.api_task = None
        self.running = False
        # Background task handles (set during runtime)
        self._hardware_task: asyncio.Task | None = None
        self._stop_task: asyncio.Task | None = None

    async def start(
        self,
        config_path: str | None = None,
        host: str = "0.0.0.0",
        port: int = 8000,
    ):
        """Start all application tasks."""
        try:
            # Load configuration
            self.config = load_config(config_path)
            logger = logging.getLogger(__name__)
            logger.info(
                f"Loaded config: {self.config.width}x{self.config.height} display"
            )
            logger.info(
                f"Serial: {self.config.serial.port} (mock={self.config.serial.mock})"
            )

            # Create tasks
            self.pipeline = DisplayPipeline(self.config)
            self.api_task = ApiServer(self.config, self.pipeline)

            # Start tasks in order
            logger.info("Starting pipeline (idle)...")
            # Start pipeline with default animation but not playing; processes idle until play
            await self.pipeline.start(animation="bouncing_dot", params={})

            # Do not start any animation by default; user controls start/stop via API/UI

            logger.info("Starting API server...")
            self.running = True

            # Run API server (this blocks)
            await self.api_task.start_server(host=host, port=port)

        except Exception:
            # Caller (main) decides severity and logs with broader context.
            await self.stop()
            raise

    async def stop(self):
        """Stop all application tasks."""
        if not self.running:
            return

        logger = logging.getLogger(__name__)
        logger.info("Shutting down application...")

        self.running = False

        # Stop tasks in reverse order
        if getattr(self, "pipeline", None):
            await self.pipeline.stop()

        logger.info("Application shutdown complete")


async def main():
    """Main entry point."""
    # Parse command line arguments first to get log level
    parser = argparse.ArgumentParser(description="Flip-disc display controller")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument(
        "--workers", type=int, default=1, help="Number of worker processes"
    )
    parser.add_argument("--port", type=int, default=8000, help="API server port")
    parser.add_argument("--host", default="0.0.0.0", help="API server host")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    # Set up logging with specified level
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    app = FlipDiscApplication()

    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, _frame):
        logger.info(f"Received signal {signum}, shutting down...")
        app._stop_task = asyncio.create_task(app.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Ensure consistent semantics across platforms, prefer 'fork' on macOS
        method = "fork" if sys.platform == "darwin" else "spawn"
        mp.set_start_method(method, force=True)
        await app.start(
            config_path=args.config,
            host=args.host,
            port=args.port,
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
