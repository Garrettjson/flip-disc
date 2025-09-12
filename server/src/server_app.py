"""
ServerApp - Composition Root

This module contains the ServerApp class, which is responsible for:
- FastAPI application setup and configuration
- Dependency injection and component wiring
- Application lifecycle management (startup/shutdown)
- Health monitoring and statistics

Composition root - wires up all components with proper dependency injection.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import DisplayConfig, load_from_toml, default_config
from .frame_buffer import AsyncFrameBuffer
from .display_controller import DisplayController
from .frame_mapper import FrameMapper
from .protocol_encoder import ProtocolEncoder
from .serial_port import create_serial_port


logger = logging.getLogger(__name__)


class ServerApp:
    """
    Application composition root for flip-disc server.

    Handles FastAPI setup, dependency injection, and lifecycle management.
    Replaces the god object FlipDiscServer with proper separation of concerns.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("config.toml")

        # Core components - initialized during startup
        self.display_config: Optional[DisplayConfig] = None
        self.frame_mapper: Optional[FrameMapper] = None
        self.protocol_encoder: Optional[ProtocolEncoder] = None
        self.display_controller: Optional[DisplayController] = None
        self.frame_buffer: Optional[AsyncFrameBuffer] = None

        # Application state
        self.display_running = False
        self._display_task: Optional[asyncio.Task] = None

        # FastAPI app
        self.app: Optional[FastAPI] = None
        self._started: bool = False

        logger.info(f"ServerApp initialized with config: {self.config_path}")

    async def startup(self) -> None:
        """Initialize all application components with proper dependency injection."""
        logger.info("Starting up server application...")

        try:
            # Load configuration
            await self._load_configuration()

            # Create pure logic components
            await self._create_pure_components()

            # Create I/O boundary and policy layer
            await self._create_display_controller()

            # Create frame buffer
            await self._create_frame_buffer()

            # Connect to hardware
            await self._connect_hardware()

            # Create FastAPI app with dependency injection
            await self._create_fastapi_app()

            logger.info("Server application startup completed successfully")
            self._started = True

        except Exception as e:
            logger.error(f"Server application startup failed: {e}")
            await self.shutdown()  # Cleanup on failure
            raise

    async def shutdown(self) -> None:
        """Cleanup all application components."""
        logger.info("Shutting down server application...")

        try:
            # Stop display loop
            await self.stop_display_loop()

            # Disconnect from hardware
            if self.display_controller:
                await self.display_controller.disconnect()

            # Clear frame buffer
            if self.frame_buffer:
                await self.frame_buffer.clear_buffer()

            logger.info("Server application shutdown completed")
            self._started = False

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

    async def start_display_loop(self) -> bool:
        """Start the main display loop with proper error handling."""
        if self.display_running:
            logger.warning("Display loop already running")
            return True

        if not self.frame_buffer or not self.display_controller:
            logger.error("Components not initialized - cannot start display loop")
            return False

        logger.info("Starting display loop...")

        try:
            # Create display callback that uses our clean architecture
            async def display_callback(frame):
                try:
                    if self.display_controller is not None:
                        await self.display_controller.send_canvas_frame(frame.data)
                    else:
                        logger.error("Display controller is not initialized")
                    # Broadcast updated credits and status to WS clients after consuming a frame
                    if self.frame_buffer is not None:
                        try:
                            from .api import connection_manager

                            credits = await self.frame_buffer.get_credits()
                            status = self.frame_buffer.get_buffer_status()
                            await connection_manager.broadcast_message(
                                {
                                    "type": "credits",
                                    "credits": credits,
                                    "buffer_level": status.get("buffer_utilization", 0.0),
                                    "timestamp": asyncio.get_event_loop().time(),
                                }
                            )
                            await connection_manager.broadcast_message(
                                {
                                    "type": "status",
                                    "fps_actual": status.get("fps_actual", 0.0),
                                    "buffer_level": status.get("buffer_utilization", 0.0),
                                    "frames_displayed": status.get("stats", {}).get("frames_displayed", 0),
                                    "timestamp": asyncio.get_event_loop().time(),
                                }
                            )
                        except Exception as be:
                            logger.debug(f"Broadcast credits/status failed: {be}")
                except Exception as e:
                    logger.error(f"Error in display callback: {e}")

            # Start the display loop
            self._display_task = asyncio.create_task(
                self.frame_buffer.start_display_loop(display_callback)
            )

            self.display_running = True
            logger.info("Display loop started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start display loop: {e}")
            return False

    async def stop_display_loop(self) -> None:
        """Stop the display loop gracefully."""
        if not self.display_running:
            return

        logger.info("Stopping display loop...")

        try:
            # Stop the frame buffer loop
            if self.frame_buffer:
                await self.frame_buffer.stop_display_loop()

            # Cancel the display task
            if self._display_task and not self._display_task.done():
                self._display_task.cancel()
                try:
                    await self._display_task
                except asyncio.CancelledError:
                    pass  # Expected when cancelling

            # Clear buffer and reset credits
            if self.frame_buffer:
                try:
                    cleared = await self.frame_buffer.clear_buffer()
                    logger.info(f"Cleared {cleared} frames from buffer on stop")
                except Exception as e:
                    logger.error(f"Failed to clear buffer on stop: {e}")

            self.display_running = False
            logger.info("Display loop stopped")

            # Broadcast final credits/status
            try:
                from .api import connection_manager

                if self.frame_buffer:
                    status = self.frame_buffer.get_buffer_status()
                    credits = await self.frame_buffer.get_credits()
                else:
                    status = {"buffer_utilization": 0.0, "fps_actual": 0.0}
                    credits = 0

                await connection_manager.broadcast_message(
                    {
                        "type": "credits",
                        "credits": credits,
                        "buffer_level": status.get("buffer_utilization", 0.0),
                        "timestamp": asyncio.get_event_loop().time(),
                    }
                )
                await connection_manager.broadcast_message(
                    {
                        "type": "status",
                        "fps_actual": 0.0,
                        "buffer_level": status.get("buffer_utilization", 0.0),
                        "frames_displayed": status.get("stats", {}).get("frames_displayed", 0),
                        "timestamp": asyncio.get_event_loop().time(),
                        "running": False,
                    }
                )
            except Exception as e:
                logger.debug(f"Broadcast on stop failed: {e}")

        except Exception as e:
            logger.error(f"Error stopping display loop: {e}")

    def get_fastapi_app(self) -> FastAPI:
        """Get the FastAPI application instance."""
        if not self.app:
            raise RuntimeError("FastAPI app not initialized - call startup() first")
        return self.app

    # Private initialization methods

    async def _load_configuration(self) -> None:
        """Load display configuration from file or use defaults."""
        if self.config_path.exists():
            logger.info(f"Loading configuration from {self.config_path}")
            self.display_config = load_from_toml(self.config_path)
        else:
            logger.warning(
                f"Config file {self.config_path} not found, using default configuration"
            )
            self.display_config = default_config()

    async def _create_pure_components(self) -> None:
        """Create pure logic components (no I/O dependencies)."""
        self.frame_mapper = FrameMapper()
        self.protocol_encoder = ProtocolEncoder()
        logger.debug("Created pure logic components")

    async def _create_display_controller(self) -> None:
        """Create display controller with dependency injection."""
        if not self.display_config:
            raise RuntimeError("Display config not loaded")

        # Create serial port I/O boundary
        serial_port = create_serial_port(self.display_config.serial)

        # Create display controller with all dependencies
        self.display_controller = DisplayController(
            display_config=self.display_config,
            frame_mapper=self.frame_mapper,
            protocol_encoder=self.protocol_encoder,
            serial_port=serial_port,
        )
        logger.debug("Created display controller with dependency injection")

    async def _create_frame_buffer(self) -> None:
        """Create frame buffer component."""
        if not self.display_config:
            raise RuntimeError("Display config not loaded")

        self.frame_buffer = AsyncFrameBuffer(self.display_config)
        logger.debug("Created frame buffer")

    async def _connect_hardware(self) -> None:
        """Connect to display hardware."""
        if not self.display_controller:
            raise RuntimeError("Display controller not created")

        await self.display_controller.connect()
        logger.debug("Connected to display hardware")

    async def _create_fastapi_app(self) -> None:
        """Create FastAPI application with proper dependency injection."""

        # Create lifespan context manager
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            started_here = False
            if not self._started:
                await self.startup()
                started_here = True
            try:
                yield
            finally:
                if started_here and self._started:
                    await self.shutdown()

        # Create FastAPI app
        self.app = FastAPI(
            title="Flip Disc Display Server",
            description="REST and WebSocket API for flip disc display control",
            version="2.0.0",
            lifespan=lifespan,
        )

        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=self._allowed_origins(),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Import and include API routes with dependency injection
        from .api import router, get_server, websocket_endpoint

        # Override the get_server dependency to return our components
        def get_server_override():
            if (
                not self.display_controller
                or not self.frame_buffer
                or not self.display_config
            ):
                raise RuntimeError("Server components not initialized")

            # Create a server-like object for compatibility
            class ServerComponents:
                def __init__(self, server_app):
                    self._server_app = server_app
                    self.display_config = server_app.display_config
                    self.frame_buffer = server_app.frame_buffer
                    self.serial_controller = (
                        server_app.display_controller
                    )  # Backward compatibility
                    self.display_controller = server_app.display_controller
                    self.display_running = server_app.display_running

                def get_stats(self):
                    return self._server_app.get_stats()

                # Pass-through controls
                async def start_display_loop(self) -> bool:
                    return await self._server_app.start_display_loop()

                async def stop_display_loop(self) -> None:
                    await self._server_app.stop_display_loop()

            return ServerComponents(self)

        # Override the dependency
        self.app.dependency_overrides[get_server] = get_server_override

        # Attach server instance for WebSocket access and include routes
        self.app.state.server = self
        self.app.include_router(router, prefix="/api")
        self.app.add_api_websocket_route("/ws/frames", websocket_endpoint)

        logger.debug("Created FastAPI application with dependency injection")

    def _allowed_origins(self) -> list[str]:
        import os
        raw = os.getenv("ALLOWED_ORIGINS", "*")
        raw = raw.strip()
        if raw == "*" or raw == "":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    def get_stats(self) -> dict:
        if (
            not self.display_controller
            or not self.frame_buffer
            or not self.display_config
        ):
            return {"running": False, "message": "server not initialized"}

        status = self.frame_buffer.get_buffer_status()
        health = self.frame_buffer.get_buffer_health()
        display = self.display_controller.get_display_stats()

        return {
            "running": self.display_running,
            "buffer": status,
            "health": health,
            "display": display,
        }
