"""API task - FastAPI server for control and status."""

import logging

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

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
        # Mount static assets for UI
        web_dir = Path(__file__).resolve().parent.parent / "web"
        static_dir = web_dir / "static"
        if static_dir.exists():
            self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
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

        @self.app.post("/animations/configure")
        async def configure_animation(params: dict):
            try:
                await self.worker_manager.configure_animation(params)
                return {"message": "Configured current animation", "params": params}
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

        @self.app.post("/animations/stop")
        async def stop_animation():
            try:
                await self.worker_manager.pause()
                return {"message": "Animation stopped"}
            except Exception as e:
                logger.error(f"Error stopping animation: {e}")
                raise HTTPException(500, f"Failed to stop animation: {e}") from e

        # Snapshot endpoint removed to avoid ad-hoc behavior; rely on start/stop semantics

        @self.app.post("/display/test/{pattern}")
        async def display_test_pattern(pattern: str):
            if not self.hardware_task.running:
                raise HTTPException(400, "Hardware not running")

            # Supported patterns are generated by workers
            if pattern not in ["checkerboard", "solid", "clear"]:
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

        # Simple UI route (serves index.html if present)
        @self.app.get("/ui")
        async def ui():
            web_dir = Path(__file__).resolve().parent.parent / "web"
            index_file = web_dir / "index.html"
            if index_file.exists():
                return HTMLResponse(index_file.read_text(encoding="utf-8"))
            raise HTTPException(404, "UI not available")

        # Preview route returns latest frame bits for a small canvas preview
        @self.app.get("/preview")
        async def preview():
            bits = self.hardware_task.get_last_frame_bits()
            if bits is None:
                # Provide an empty frame if none yet
                return JSONResponse(
                    {
                        "width": self.config.width,
                        "height": self.config.height,
                        "bits": [],
                    }
                )
            # Convert to compact list-of-rows (0/1)
            rows = bits.astype(int).tolist()
            return JSONResponse(
                {
                    "width": bits.shape[1],
                    "height": bits.shape[0],
                    "bits": rows,
                }
            )

        # Alias endpoint: singular form for convenience
        @self.app.post("/anim/{name}")
        async def start_animation_alias(name: str):
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

        # Refresh rate endpoints
        @self.app.get("/fps")
        async def get_fps():
            return {"refresh_rate": self.config.refresh_rate}

        @self.app.post("/fps")
        async def set_fps(new_fps: float):
            try:
                await self.hardware_task.set_refresh_rate(new_fps)
                return {"message": "Refresh rate updated", "refresh_rate": new_fps}
            except Exception as e:
                logger.error(f"Error setting refresh rate: {e}")
                raise HTTPException(400, f"Failed to set refresh rate: {e}") from e

        @self.app.post("/serial/reconnect")
        async def serial_reconnect():
            try:
                await self.hardware_task.reconnect_serial()
                return {"message": "Serial reconnected"}
            except Exception as e:
                logger.error(f"Error reconnecting serial: {e}")
                raise HTTPException(500, f"Failed to reconnect serial: {e}") from e

    async def start_server(self, host: str = "0.0.0.0", port: int = 8000):
        """Start the API server."""
        config = uvicorn.Config(self.app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)

        logger.info(f"Starting API server on {host}:{port}")
        await server.serve()
