"""API server for control and status (FastAPI)."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from flipdisc.config import DisplayConfig
from flipdisc.core.exceptions import AnimationError

from .pipeline import DisplayPipeline

logger = logging.getLogger(__name__)


class ApiServer:
    """FastAPI server for flip-disc control."""

    def __init__(self, config: DisplayConfig, pipeline: DisplayPipeline) -> None:
        self.config = config
        self.pipeline = pipeline

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
                st = self.pipeline.get_status()

                return {
                    "pipeline": {
                        "running": st.running,
                        "playing": st.playing,
                        "frames_presented": st.frames_presented,
                        "raw_ring": st.raw_ring,
                        "ready_ring": st.ready_ring,
                        "serial_connected": self.pipeline.serial.is_connected(),
                    },
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
                animations = list_animations()
                return {"animations": animations}
            except Exception as e:
                logger.error(f"Error listing animations: {e}")
                raise HTTPException(500, f"Failed to list animations: {e}") from e

        @self.app.post("/animations/{name}/start")
        async def start_animation(name: str):
            try:
                # Ensure pipeline started (processes running)
                if not self.pipeline.running:
                    await self.pipeline.start(animation=name)
                await self.pipeline.set_animation(name)
                await self.pipeline.play()
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
                # For now, reapply animation with new params (restart generator)
                # If no current animation context, start pipeline with defaults
                name = params.pop("name", "bouncing_dot")
                if not self.pipeline.running:
                    await self.pipeline.start(animation=name, params=params)
                else:
                    await self.pipeline.set_animation(name, params)
                return {"message": "Configured animation", "params": params}
            except AnimationError as e:
                logger.error(f"Animation configuration error: {e}")
                raise HTTPException(400, str(e)) from e
            except Exception as e:
                logger.error(f"Unexpected error configuring animation: {e}")
                raise HTTPException(500, f"Failed to configure animation: {e}") from e

        @self.app.post("/animations/reset")
        async def reset_animation():
            try:
                await self.pipeline.reset()
                return {"message": "Animation reset"}
            except Exception as e:
                logger.error(f"Error resetting animation: {e}")
                raise HTTPException(500, f"Failed to reset animation: {e}") from e

        @self.app.post("/animations/stop")
        async def stop_animation():
            try:
                await self.pipeline.pause()
                return {"message": "Animation stopped"}
            except Exception as e:
                logger.error(f"Error stopping animation: {e}")
                raise HTTPException(500, f"Failed to stop animation: {e}") from e

        # Alias endpoint: singular form for convenience
        @self.app.post("/anim/{name}")
        async def start_animation_alias(name: str):
            try:
                if not self.pipeline.running:
                    await self.pipeline.start(animation=name)
                await self.pipeline.set_animation(name)
                await self.pipeline.play()
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
                await self.pipeline.set_refresh_rate(new_fps)
                return {"message": "Refresh rate updated", "refresh_rate": new_fps}
            except Exception as e:
                logger.error(f"Error setting refresh rate: {e}")
                raise HTTPException(400, f"Failed to set refresh rate: {e}") from e

        @self.app.post("/serial/reconnect")
        async def serial_reconnect():
            try:
                await self.pipeline.reconnect_serial()
                return {"message": "Serial reconnected"}
            except Exception as e:
                logger.error(f"Error reconnecting serial: {e}")
                raise HTTPException(500, f"Failed to reconnect serial: {e}") from e

        @self.app.post("/display/test/{pattern}")
        async def display_test_pattern(pattern: str):
            if pattern not in ["checkerboard", "solid", "clear"]:
                raise HTTPException(400, f"Unknown pattern: {pattern}")

            try:
                # Use pipeline set_animation with synthetic test generators in the future.
                # For now this endpoint is a no-op or could be implemented via restarting with a test pattern.
                return {"message": f"Test pattern endpoint pending: {pattern}"}
            except Exception as e:
                logger.error(f"Error displaying test pattern: {e}")
                raise HTTPException(500, f"Failed to display pattern: {e}") from e

        # WebSocket preview endpoint
        @self.app.websocket("/ws/preview")
        async def preview_websocket(websocket: WebSocket):
            await websocket.accept()

            # Use asyncio Event to signal when new frames are available
            frame_available = asyncio.Event()

            def frame_callback(_bits):
                # Just signal that a new frame is available, don't serialize yet
                frame_available.set()

            # Register callback with display pacer
            self.pipeline.set_preview_callback(frame_callback)

            try:
                while True:
                    # Wait for new frame signal
                    await frame_available.wait()
                    frame_available.clear()

                    # Get the latest frame from ring buffer and serialize only now
                    bits = self.pipeline.get_last_frame_bits()
                    if bits is not None:
                        # Convert to format expected by JavaScript
                        rows = bits.astype(int).tolist()
                        preview_data = {
                            "width": bits.shape[1],
                            "height": bits.shape[0],
                            "bits": rows,
                        }
                        await websocket.send_text(json.dumps(preview_data))

            except WebSocketDisconnect:
                logger.debug("Preview WebSocket client disconnected")
            except Exception as e:
                logger.error(f"Preview WebSocket error: {e}")
            finally:
                # Unregister callback when client disconnects
                self.pipeline.set_preview_callback(None)

        # UI index
        @self.app.get("/ui")
        async def ui():
            web_dir = Path(__file__).resolve().parent.parent / "web"
            index_file = web_dir / "index.html"
            if index_file.exists():
                return HTMLResponse(index_file.read_text(encoding="utf-8"))
            raise HTTPException(404, "UI not available")

    async def start_server(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        config = uvicorn.Config(self.app, host=host, port=port, log_level="warning")
        server = uvicorn.Server(config)
        logger.info(f"Starting API server on {host}:{port}")
        await server.serve()
