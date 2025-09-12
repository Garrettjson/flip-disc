#!/usr/bin/env python3
"""
Flip Disc Server - Main Application Entry Point

Provides backward compatibility wrapper around the new ServerApp architecture.
For new code, use ServerApp directly.
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

from .server_app import ServerApp

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FlipDiscServer:
    """
    DEPRECATED: Backward compatibility wrapper around ServerApp.

    Use ServerApp directly for new code.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize FlipDiscServer (delegates to ServerApp)."""
        self._server_app = ServerApp(config_path)

        # Backward compatibility properties
        self.config_path = config_path or Path("config.toml")

    async def startup(self) -> None:
        """Initialize all server components."""
        await self._server_app.startup()

        # Set backward compatibility properties
        self.display_config = self._server_app.display_config
        self.frame_buffer = self._server_app.frame_buffer
        self.serial_controller = self._server_app.display_controller

    async def shutdown(self) -> None:
        """Cleanup all server components."""
        await self._server_app.shutdown()

    async def start_display_loop(self) -> bool:
        """Start the main display loop."""
        return await self._server_app.start_display_loop()

    async def stop_display_loop(self) -> None:
        """Stop the display loop."""
        await self._server_app.stop_display_loop()

    @property
    def display_running(self) -> bool:
        """Check if display loop is running."""
        return self._server_app.display_running

    def get_fastapi_app(self) -> FastAPI:
        """Get the FastAPI application instance."""
        return self._server_app.get_fastapi_app()


# Global server instance for FastAPI lifespan
server_instance: Optional[ServerApp] = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    """FastAPI lifespan context manager."""
    global server_instance
    try:
        logger.info("Application starting...")
        server_instance = ServerApp()
        await server_instance.startup()
        yield
    finally:
        logger.info("Application shutting down...")
        if server_instance:
            await server_instance.shutdown()


def create_app(config_path: Optional[Path] = None) -> FastAPI:
    """Create FastAPI application with proper configuration."""
    global server_instance

    # Create server app
    server_instance = ServerApp(config_path)

    # Create FastAPI app with lifespan
    app = FastAPI(
        title="Flip Disc Display Server",
        description="REST and WebSocket API for flip disc display control",
        version="2.0.0",
        lifespan=lifespan,
    )

    return app


def get_server() -> ServerApp:
    """Dependency function to get server instance."""
    global server_instance
    if server_instance is None:
        raise RuntimeError("Server not initialized")
    return server_instance


async def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    config_path: Optional[str] = None,
    reload: bool = False,
) -> None:
    """Run the server with the given configuration."""

    config_path_obj = Path(config_path) if config_path else None

    if reload:
        # Development mode with hot reload
        uvicorn.run(
            "src.main:create_app", host=host, port=port, reload=True, factory=True
        )
    else:
        # Production mode - manual startup/shutdown
        global server_instance
        server_instance = ServerApp(config_path_obj)

        try:
            # Startup server components
            await server_instance.startup()

            # Get FastAPI app
            app = server_instance.get_fastapi_app()

            # Setup signal handlers for graceful shutdown
            def signal_handler(sig, _):
                logger.info(f"Received signal {sig}, shutting down...")
                sys.exit(0)

            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            # Run server
            config = uvicorn.Config(app=app, host=host, port=port, log_level="info")
            server = uvicorn.Server(config)

            logger.info(f"Starting server on {host}:{port}")
            await server.serve()

        except Exception as e:
            logger.error(f"Server failed: {e}")
            raise
        finally:
            if server_instance:
                await server_instance.shutdown()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Flip Disc Display Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--config", help="Path to configuration file")
    parser.add_argument(
        "--reload", action="store_true", help="Enable hot reload (development)"
    )

    args = parser.parse_args()

    try:
        asyncio.run(
            run_server(
                host=args.host,
                port=args.port,
                config_path=args.config,
                reload=args.reload,
            )
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)
