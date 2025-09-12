#!/usr/bin/env python3
"""
Flip Disc Server - Main Application Entry Point

Application factory to build and run the FastAPI app backed by ServerApp.
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


server_instance: Optional[ServerApp] = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    """FastAPI lifespan context manager (unused here; app defines its own)."""
    yield


def create_app(config_path: Optional[Path] = None) -> FastAPI:
    """Uvicorn factory: build app; ServerApp handles startup via lifespan."""
    global server_instance
    server_instance = ServerApp(config_path)
    # Create the FastAPI app without performing startup here
    # (ServerApp's lifespan will call startup/shutdown).
    asyncio.run(server_instance._create_fastapi_app())
    return server_instance.get_fastapi_app()


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
