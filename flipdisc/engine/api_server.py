"""API server for control and status (FastAPI)."""

from __future__ import annotations

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import DisplayConfig
from ..core.exceptions import AnimationError
from .display_pacer import DisplayPacer
from .worker_pool import AnimationWorkerPool

logger = logging.getLogger(__name__)


class ApiServer:
    """FastAPI server for flip-disc control."""

    def __init__(
        self,
        config: DisplayConfig,
        display_pacer: DisplayPacer,
        worker_pool: AnimationWorkerPool,
    ) -> None:
        self.config = config
        self.display_pacer = display_pacer
        self.worker_pool = worker_pool

        self.app = FastAPI(title="Flip-Disc Controller", version="0.2.0")
        # Mount static assets for UI
        web_dir = Path(__file__).resolve().parent.parent / "web"
        static_dir = web_dir / "static"
        if static_dir.exists():
            self.app.mount(
                "/static", StaticFiles(directory=str(static_dir)), name="static"
            )
        self._setup_routes()

    def _setup_routes(self) -> None:  # noqa: PLR0915
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
                hardware_status = self.display_pacer.get_status()
                worker_status = self.worker_pool.get_status()

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
                animations = await self.worker_pool.list_animations()
                return {"animations": animations}
            except Exception as e:
                logger.error(f"Error listing animations: {e}")
                raise HTTPException(500, f"Failed to list animations: {e}") from e

        @self.app.post("/animations/{name}/start")
        async def start_animation(name: str):
            if not self.display_pacer.running:
                raise HTTPException(400, "Hardware not running")

            try:
                await self.worker_pool.set_animation(name)
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
                await self.worker_pool.configure_animation(params)
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
                await self.worker_pool.reset_animation()
                return {"message": "Animation reset"}
            except Exception as e:
                logger.error(f"Error resetting animation: {e}")
                raise HTTPException(500, f"Failed to reset animation: {e}") from e

        @self.app.post("/animations/stop")
        async def stop_animation():
            try:
                await self.worker_pool.pause()
                return {"message": "Animation stopped"}
            except Exception as e:
                logger.error(f"Error stopping animation: {e}")
                raise HTTPException(500, f"Failed to stop animation: {e}") from e

        # Alias endpoint: singular form for convenience
        @self.app.post("/anim/{name}")
        async def start_animation_alias(name: str):
            if not self.display_pacer.running:
                raise HTTPException(400, "Hardware not running")
            try:
                await self.worker_pool.set_animation(name)
                return {"message": f"Started animation: {name}"}
            except AnimationError as e:
                logger.error(f"Animation error: {e}")
                raise HTTPException(400, str(e)) from e
            except Exception as e:
                logger.error(f"Unexpected error starting animation: {e}")
                raise HTTPException(500, f"Failed to start animation: {e}") from e

        @self.app.get("/fps")
        async def get_fps():
            return {"refresh_rate": self.config.refresh_rate}

        @self.app.post("/fps")
        async def set_fps(new_fps: float):
            try:
                await self.display_pacer.set_refresh_rate(new_fps)
                return {"message": "Refresh rate updated", "refresh_rate": new_fps}
            except Exception as e:
                logger.error(f"Error setting refresh rate: {e}")
                raise HTTPException(400, f"Failed to set refresh rate: {e}") from e

        @self.app.post("/serial/reconnect")
        async def serial_reconnect():
            try:
                await self.display_pacer.reconnect_serial()
                return {"message": "Serial reconnected"}
            except Exception as e:
                logger.error(f"Error reconnecting serial: {e}")
                raise HTTPException(500, f"Failed to reconnect serial: {e}") from e

        @self.app.post("/display/test/{pattern}")
        async def display_test_pattern(pattern: str):
            if not self.display_pacer.running:
                raise HTTPException(400, "Hardware not running")

            if pattern not in ["checkerboard", "solid", "clear"]:
                raise HTTPException(400, f"Unknown pattern: {pattern}")

            try:
                await self.worker_pool.display_test_pattern(pattern)
                return {"message": f"Displaying {pattern} pattern"}
            except Exception as e:
                logger.error(f"Error displaying test pattern: {e}")
                raise HTTPException(500, f"Failed to display pattern: {e}") from e

        # UI index
        @self.app.get("/ui")
        async def ui():
            web_dir = Path(__file__).resolve().parent.parent / "web"
            index_file = web_dir / "index.html"
            if index_file.exists():
                return HTMLResponse(index_file.read_text(encoding="utf-8"))
            raise HTTPException(404, "UI not available")

        # Preview endpoint
        @self.app.get("/preview")
        async def preview():
            bits = self.display_pacer.get_last_frame_bits()
            if bits is None:
                return JSONResponse(
                    {
                        "width": self.config.width,
                        "height": self.config.height,
                        "bits": [],
                    }
                )
            rows = bits.astype(int).tolist()
            return JSONResponse(
                {
                    "width": bits.shape[1],
                    "height": bits.shape[0],
                    "bits": rows,
                }
            )

    async def start_server(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        config = uvicorn.Config(self.app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        logger.info(f"Starting API server on {host}:{port}")
        await server.serve()
