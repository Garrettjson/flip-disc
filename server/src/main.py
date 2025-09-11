#!/usr/bin/env python3
"""
Flip Disc Server - Main Application Entry Point

Manages serial communication and frame buffering for flip disc displays.
Provides REST and WebSocket APIs for orchestrator communication.
"""

import asyncio
import logging
import signal
import sys
import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import (
    DisplayConfig,
    load_from_toml,
    default_config,
)
from .frame_buffer import AsyncFrameBuffer
from .serial_controller import SerialController

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FlipDiscServer:
    """
    Main server application managing all components.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("config.toml")

        # Core components - initialized in startup
        self.display_config: Optional[DisplayConfig] = None
        self.frame_buffer: Optional[AsyncFrameBuffer] = None
        self.serial_controller: Optional[SerialController] = None

        # Application state
        self.display_running = False
        self._display_task: Optional[asyncio.Task] = None

        logger.info(f"Flip disc server initialized with config: {self.config_path}")

    async def startup(self) -> None:
        """Initialize all server components."""
        logger.info("Starting up flip disc server...")

        try:
            # Load configuration
            if self.config_path.exists():
                logger.info(f"Loading configuration from {self.config_path}")
                self.display_config = load_from_toml(self.config_path)
            else:
                logger.warning(
                    f"Config file {self.config_path} not found, using default configuration"
                )
                self.display_config = default_config()

            # Initialize frame buffer
            self.frame_buffer = AsyncFrameBuffer(self.display_config)

            # Initialize serial controller
            self.serial_controller = SerialController(self.display_config)

            # Connect to serial interface
            await self.serial_controller.connect()

            logger.info("Server startup completed successfully")

        except Exception as e:
            logger.error(f"Server startup failed: {e}")
            raise

    async def shutdown(self) -> None:
        """Cleanup all server components."""
        logger.info("Shutting down flip disc server...")

        # Stop display loop
        await self.stop_display_loop()

        # Disconnect serial controller
        if self.serial_controller:
            await self.serial_controller.disconnect()

        # Clear frame buffer
        if self.frame_buffer:
            await self.frame_buffer.clear_buffer()

        logger.info("Server shutdown completed")

    async def start_display_loop(self) -> bool:
        """Start the main display loop."""
        if self.display_running:
            logger.warning("Display loop already running")
            return True

        if not self.frame_buffer or not self.serial_controller:
            logger.error("Components not initialized")
            return False

        logger.info("Starting display loop...")

        # Create display callback
        async def display_callback(frame):
            try:
                # Send frame to display
                if self.serial_controller is not None:
                    await self.serial_controller.send_canvas_frame(frame.data)
                else:
                    logger.error("Serial controller is not initialized (None)")
            except Exception as e:
                logger.error(f"Error in display callback: {e}")

        # Start the display loop
        self._display_task = asyncio.create_task(
            self.frame_buffer.start_display_loop(display_callback)
        )

        self.display_running = True
        logger.info("Display loop started")
        return True

    async def stop_display_loop(self) -> None:
        """Stop the display loop."""
        if not self.display_running:
            return

        logger.info("Stopping display loop...")

        # Stop the frame buffer loop
        if self.frame_buffer:
            await self.frame_buffer.stop_display_loop()

        # Cancel the display task
        if self._display_task and not self._display_task.done():
            self._display_task.cancel()
            try:
                await self._display_task
            except asyncio.CancelledError:
                pass

        self.display_running = False
        logger.info("Display loop stopped")

    def get_stats(self) -> dict:
        """Get server statistics."""
        stats = {
            "running": self.display_running,
            "config_path": str(self.config_path),
        }

        if self.display_config:
            stats["display"] = {
                "canvas_size": f"{self.display_config.canvas_size.w}x{self.display_config.canvas_size.h}",
                "panel_count": len(self.display_config.panels),
                "refresh_rate": self.display_config.refresh_rate,
            }

        if self.frame_buffer:
            stats["buffer"] = self.frame_buffer.get_buffer_status()
            stats["buffer_health"] = self.frame_buffer.get_buffer_health()

        if self.serial_controller:
            stats["serial"] = {
                "connected": self.serial_controller.is_connected(),
                "port": (
                    self.display_config.serial.port if self.display_config else None
                ),
                "mock": (
                    self.display_config.serial.mock if self.display_config else None
                ),
            }

        return stats


# Global server instance
server: Optional[FlipDiscServer] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    global server
    # Startup
    try:
        server = FlipDiscServer()

        # Make the server instance available on the app state immediately so
        # FastAPI dependencies (which read `request.app.state.server`) won't
        # fail with an AttributeError if a request arrives during startup.
        app.state.server = server

        # Perform potentially-failing initialization after the instance is
        # attached to app.state. If initialization fails we'll still surface
        # the error and prevent the app from serving successfully.
        await server.startup()

        # Start display loop
        await server.start_display_loop()

        yield

    finally:
        # Shutdown
        try:
            if getattr(app.state, "server", None):
                await app.state.server.shutdown()
        except Exception:
            logger.exception("Error during server shutdown")

        # Clear from both module global and app state
        server = None
        if hasattr(app.state, "server"):
            delattr(app.state, "server")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Flip Disc Server",
        description="Server for managing flip disc display panels",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Configure CORS for orchestrator communication
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import and include API routes
    from .api import router as api_router

    app.include_router(api_router, prefix="/api")

    # Add root endpoint
    @app.get("/")
    async def root():
        return {
            "message": "Flip Disc Server is running. See /docs for API documentation."
        }

    # Import and setup WebSocket
    from .api import websocket_endpoint

    app.add_websocket_route("/ws/frames", websocket_endpoint)

    return app


def main():
    """Main entry point."""

    # Handle graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create app
    app = create_app()

    config = uvicorn.Config(
        app=app, host="0.0.0.0", port=8000, log_level="info", access_log=True
    )
    server = uvicorn.Server(config)

    try:
        logger.info("Starting flip disc server on http://0.0.0.0:8000")
        server.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
