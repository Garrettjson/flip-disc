"""API task - FastAPI server for control and status."""

import logging

import uvicorn
from fastapi import FastAPI, HTTPException

from ..config import DisplayConfig
from ..exceptions import AnimationError
from .hardware import HardwareTask
from .worker_manager import WorkerManager

logger = logging.getLogger(__name__)


class APITask:
    """
    FastAPI server task for flip-disc control.

    This task provides REST API endpoints for:
    - System status and control
    - Animation control
    - Test patterns
    - Worker management
    """

    def __init__(
        self,
        config: DisplayConfig,
        hardware_task: HardwareTask,
        worker_manager: WorkerManager,
    ):
        self.config = config
        self.hardware_task = hardware_task
        self.worker_manager = worker_manager

        self.app = FastAPI(title="Flip-Disc Controller", version="0.2.0")
        self._setup_routes()

    def _setup_routes(self):  # noqa: PLR0915
        """Set up API routes."""

        @self.app.get("/")
        async def root():
            return {
                "message": "Flip-Disc Controller",
                "version": "0.2.0",
                "status": "running",
            }

        @self.app.get("/status")
        async def status():
            try:
                hardware_status = self.hardware_task.get_status()
                worker_status = self.worker_manager.get_status()

                return {
                    "hardware": hardware_status,
                    "workers": worker_status,
                    "config": {
                        "width": self.config.width,
                        "height": self.config.height,
                        "refresh_rate": self.config.refresh_rate,
                    },
                }
            except Exception as e:
                logger.error(f"Error getting status: {e}")
                raise HTTPException(500, f"Status error: {e}") from e

        @self.app.get("/animations")
        async def list_animations():
            try:
                animations = await self.worker_manager.list_animations()
                return {"animations": animations}
            except Exception as e:
                logger.error(f"Error listing animations: {e}")
                raise HTTPException(500, f"Failed to list animations: {e}") from e

        @self.app.post("/animations/{name}/start")
        async def start_animation(name: str):
            if not self.hardware_task.running:
                raise HTTPException(400, "Hardware not running")

            try:
                await self.worker_manager.set_animation(name)
                return {"message": f"Started animation: {name}"}
            except AnimationError as e:
                logger.error(f"Animation error: {e}")
                raise HTTPException(400, str(e)) from e
            except Exception as e:
                logger.error(f"Unexpected error starting animation: {e}")
                raise HTTPException(500, f"Failed to start animation: {e}") from e

        @self.app.post("/animations/{name}/configure")
        async def configure_animation(name: str, params: dict):
            try:
                await self.worker_manager.configure_animation(name, params)
                return {"message": f"Configured animation: {name}", "params": params}
            except AnimationError as e:
                logger.error(f"Animation configuration error: {e}")
                raise HTTPException(400, str(e)) from e
            except Exception as e:
                logger.error(f"Unexpected error configuring animation: {e}")
                raise HTTPException(500, f"Failed to configure animation: {e}") from e

        @self.app.post("/animations/reset")
        async def reset_animation():
            try:
                await self.worker_manager.reset_animation()
                return {"message": "Animation reset"}
            except Exception as e:
                logger.error(f"Error resetting animation: {e}")
                raise HTTPException(500, f"Failed to reset animation: {e}") from e

        @self.app.post("/display/test/{pattern}")
        async def display_test_pattern(pattern: str):
            if not self.hardware_task.running:
                raise HTTPException(400, "Hardware not running")

            if pattern not in ["checkerboard", "border", "solid", "clear"]:
                raise HTTPException(400, f"Unknown pattern: {pattern}")

            try:
                await self.worker_manager.display_test_pattern(pattern)
                return {"message": f"Displaying {pattern} pattern"}
            except Exception as e:
                logger.error(f"Error displaying test pattern: {e}")
                raise HTTPException(500, f"Failed to display pattern: {e}") from e

        @self.app.post("/display/clear")
        async def clear_display():
            return await display_test_pattern("clear")

        @self.app.post("/workers/restart")
        async def restart_workers():
            try:
                await self.worker_manager.restart_workers()
                return {"message": "Workers restarted"}
            except Exception as e:
                logger.error(f"Error restarting workers: {e}")
                raise HTTPException(500, f"Failed to restart workers: {e}") from e

    async def start_server(self, host: str = "0.0.0.0", port: int = 8000):
        """Start the API server."""
        config = uvicorn.Config(self.app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)

        logger.info(f"Starting API server on {host}:{port}")
        await server.serve()
        # Alias endpoint: singular form
        @self.app.post("/anim/{name}")
        async def start_animation_alias(name: str):
            return await start_animation(name)

        @self.app.get("/fps")
        async def get_fps():
            return {"refresh_rate": self.config.refresh_rate}

        @self.app.post("/serial/reconnect")
        async def serial_reconnect():
            try:
                await self.hardware_task.reconnect_serial()
                return {"message": "Serial reconnected"}
            except Exception as e:
                logger.error(f"Error reconnecting serial: {e}")
                raise HTTPException(500, f"Failed to reconnect serial: {e}") from e
