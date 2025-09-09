"""
Flip Disc Server API - REST and WebSocket endpoints

Provides communication interface for orchestrator:
- REST endpoints for configuration, control, and stats
- WebSocket endpoint for frame data and credit system
"""

import logging
import time
from fastapi import (
    APIRouter,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Request,
    Depends,
)
from pydantic import BaseModel
from .frame_buffer import Frame, validate_frame_for_display

try:
    from gen.py.flipdisc_frame import FlipdiscFrame
except ImportError as e:
    logging.error(f"Failed to import Kaitai parser: {e}")
    FlipdiscFrame = None

logger = logging.getLogger(__name__)

# API Router for REST endpoints
router = APIRouter()


# Dependency provider for DI
def get_server(request: Request):
    # Be defensive: the application lifespan should attach the FlipDiscServer
    # instance to `app.state.server`. However, startup can fail or requests
    # might arrive before the instance is attached. Return a clear HTTP 503
    # instead of allowing an AttributeError to bubble up.
    server = getattr(request.app.state, "server", None)
    if server is None:
        raise HTTPException(status_code=503, detail="Server not ready")
    return server


# Pydantic models for API responses
class DisplayInfo(BaseModel):
    canvas_width: int
    canvas_height: int
    panel_count: int
    refresh_rate: float
    panels: list


class ServerStatus(BaseModel):
    running: bool
    connected: bool
    buffer_level: float
    buffer_health: str
    fps: float


class ControlResponse(BaseModel):
    success: bool
    message: str


# REST API Endpoints


@router.get("/health")
async def health_check():
    """Health check endpoint for orchestrator."""
    return {"status": "healthy", "timestamp": time.time()}


@router.get("/display", response_model=DisplayInfo)
async def get_display_info(server=Depends(get_server)):
    """Get display configuration for orchestrator setup."""
    # ...existing code...
    if not server.display_config:
        raise HTTPException(status_code=500, detail="Display configuration not loaded")
    config = server.display_config
    panels = []
    for panel in config.enabled_panels:
        panels.append(
            {
                "id": panel.id,
                "address": panel.address,
                "position": {"x": panel.origin.x, "y": panel.origin.y},
                "size": {"width": panel.size.w, "height": panel.size.h},
                "orientation": panel.orientation,
            }
        )
    return DisplayInfo(
        canvas_width=config.canvas_size.w,
        canvas_height=config.canvas_size.h,
        panel_count=config.panel_count,
        refresh_rate=config.refresh_rate,
        panels=panels,
    )


@router.get("/status", response_model=ServerStatus)
async def get_server_status(server=Depends(get_server)):
    """Get current server status and buffer health."""
    # ...existing code...
    buffer_status = (
        server.frame_buffer.get_buffer_status() if server.frame_buffer else {}
    )
    buffer_health = (
        server.frame_buffer.get_buffer_health() if server.frame_buffer else {}
    )
    return ServerStatus(
        running=server.display_running,
        connected=(
            server.serial_controller.is_connected()
            if server.serial_controller
            else False
        ),
        buffer_level=buffer_status.get("buffer_utilization", 0.0),
        buffer_health=buffer_health.get("health", "unknown"),
        fps=buffer_status.get("target_fps", 0.0),
    )


@router.get("/stats")
async def get_server_stats(server=Depends(get_server)):
    """Get detailed server statistics."""
    # ...existing code...
    return server.get_stats()


@router.get("/config")
async def get_config(server=Depends(get_server)):
    """Get current display configuration."""
    # ...existing code...
    if not server.display_config:
        raise HTTPException(status_code=500, detail="Configuration not loaded")
    config = server.display_config
    return {
        "canvas": {"width": config.canvas_size.w, "height": config.canvas_size.h},
        "display": {
            "refresh_rate": config.refresh_rate,
            "buffer_duration": config.buffer_duration,
        },
        "serial": {
            "port": config.serial.port,
            "baudrate": config.serial.baudrate,
            "mock": config.serial.mock,
        },
        "panels": [
            {
                "id": panel.id,
                "address": panel.address,
                "position": {"x": panel.origin.x, "y": panel.origin.y},
                "size": {"width": panel.size.w, "height": panel.size.h},
                "orientation": panel.orientation,
                "enabled": panel.enabled,
            }
            for panel in config.panels
        ],
    }


@router.post("/control/start", response_model=ControlResponse)
async def start_display(server=Depends(get_server)):
    """Start the display loop."""
    # ...existing code...
    if server.display_running:
        return ControlResponse(success=True, message="Display loop already running")
    success = await server.start_display_loop()
    if success:
        return ControlResponse(success=True, message="Display loop started")
    else:
        raise HTTPException(status_code=500, detail="Failed to start display loop")


@router.post("/control/stop", response_model=ControlResponse)
async def stop_display(server=Depends(get_server)):
    """Stop the display loop."""
    # ...existing code...
    await server.stop_display_loop()
    return ControlResponse(success=True, message="Display loop stopped")


@router.post("/control/test/{pattern}", response_model=ControlResponse)
async def send_test_pattern(pattern: str, server=Depends(get_server)):
    """Send a test pattern to the display."""
    # ...existing code...

    if not server.serial_controller:
        raise HTTPException(status_code=500, detail="Serial controller not initialized")

    if not server.serial_controller.is_connected():
        raise HTTPException(status_code=503, detail="Serial controller not connected")

    valid_patterns = ["checkerboard", "border", "solid", "clear"]
    if pattern not in valid_patterns:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pattern '{pattern}'. Valid patterns: {valid_patterns}",
        )

    try:
        success = await server.serial_controller.send_test_pattern(pattern)

        if success:
            return ControlResponse(
                success=True, message=f"Test pattern '{pattern}' sent successfully"
            )
        else:
            raise HTTPException(
                status_code=500, detail=f"Failed to send test pattern '{pattern}'"
            )

    except Exception as e:
        logger.error(f"Error sending test pattern: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/credits")
async def get_credits(server=Depends(get_server)):
    """Get current buffer credits for orchestrator."""
    # ...existing code...
    if not server.frame_buffer:
        raise HTTPException(status_code=500, detail="Frame buffer not initialized")
    credits = await server.frame_buffer.get_credits()
    buffer_status = server.frame_buffer.get_buffer_status()
    return {
        "credits": credits,
        "buffer_level": buffer_status.get("buffer_utilization", 0.0),
        "buffer_size": buffer_status.get("buffer_size", 0),
        "max_buffer_size": buffer_status.get("max_buffer_size", 0),
        "timestamp": time.time(),
    }


# WebSocket Connection Manager
class ConnectionManager:
    """Manages WebSocket connections for frame delivery."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            f"WebSocket client connected. Active connections: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            f"WebSocket client disconnected. Active connections: {len(self.active_connections)}"
        )

    async def send_message(self, websocket: WebSocket, message: dict):
        """Send JSON message to specific client."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending message to WebSocket client: {e}")
            self.disconnect(websocket)

    async def broadcast_message(self, message: dict):
        """Broadcast JSON message to all connected clients."""
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to WebSocket client: {e}")
                disconnected.append(connection)

        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)


# Global connection manager
connection_manager = ConnectionManager()


def parse_frame_from_binary(
    data: bytes, expected_width: int, expected_height: int
) -> Frame:
    """
    Parse binary frame data using Kaitai Struct protocol.
    Format: [4B magic][2B seq][4B ts][2B width][2B height][2B payload_len][N bytes bitmap]
    """
    if FlipdiscFrame is None:
        raise ValueError("Kaitai parser not available")
    
    try:
        # Parse frame using Kaitai Struct
        parsed_frame = FlipdiscFrame.from_bytes(data)
        
        # Validate dimensions against expected values
        if parsed_frame.width != expected_width or parsed_frame.height != expected_height:
            raise ValueError(
                f"Frame dimensions {parsed_frame.width}x{parsed_frame.height} don't match expected {expected_width}x{expected_height}"
            )
        
        # Create Frame object compatible with existing system
        return Frame(
            frame_id=parsed_frame.seq,  # Use sequence number as frame ID
            flags=0,  # No flags in new binary protocol - could extend later
            width=parsed_frame.width,
            height=parsed_frame.height,
            data=parsed_frame.bitmap_data,
            timestamp=parsed_frame.timestamp,
        )
        
    except Exception as e:
        raise ValueError(f"Failed to parse frame data: {e}") from e


async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for frame data delivery and credit system.

    Protocol:
    - Orchestrator sends binary frame data
    - Server responds with JSON credit updates
    """
    server = websocket.app.state.server

    await connection_manager.connect(websocket)

    try:
        # Send initial credits
        if server.frame_buffer:
            initial_credits = await server.frame_buffer.get_credits()
            await connection_manager.send_message(
                websocket,
                {
                    "type": "credits",
                    "credits": initial_credits,
                    "buffer_level": 0.0,
                    "timestamp": time.time(),
                },
            )

        while True:
            # Receive frame data from orchestrator
            data = await websocket.receive_bytes()

            if not server.frame_buffer or not server.display_config:
                await connection_manager.send_message(
                    websocket,
                    {"type": "error", "message": "Server components not initialized"},
                )
                continue

            try:
                # Parse binary frame data
                frame = parse_frame_from_binary(
                    data,
                    server.display_config.canvas_size.w,
                    server.display_config.canvas_size.h,
                )

                # Validate frame for display
                if not validate_frame_for_display(frame, server.display_config):
                    await connection_manager.send_message(
                        websocket,
                        {
                            "type": "error",
                            "message": f"Invalid frame {frame.frame_id} for display",
                        },
                    )
                    continue

                # Add frame to buffer
                success = await server.frame_buffer.add_frame(frame)

                if success:
                    logger.debug(f"Frame {frame.frame_id} added to buffer")

                    # Send updated credits immediately
                    credits = await server.frame_buffer.get_credits()
                    buffer_status = server.frame_buffer.get_buffer_status()

                    await connection_manager.send_message(
                        websocket,
                        {
                            "type": "credits",
                            "credits": credits,
                            "buffer_level": buffer_status.get(
                                "buffer_utilization", 0.0
                            ),
                            "frame_id": frame.frame_id,
                            "timestamp": time.time(),
                        },
                    )

                else:
                    # Buffer full
                    await connection_manager.send_message(
                        websocket,
                        {
                            "type": "error",
                            "message": f"Buffer full, frame {frame.frame_id} dropped",
                            "credits": 0,
                        },
                    )

            except ValueError as e:
                logger.error(f"Invalid frame data: {e}")
                await connection_manager.send_message(
                    websocket, {"type": "error", "message": f"Invalid frame data: {e}"}
                )

            except Exception as e:
                logger.error(f"Error processing frame: {e}")
                await connection_manager.send_message(
                    websocket,
                    {"type": "error", "message": f"Error processing frame: {e}"},
                )

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")

    except Exception as e:
        logger.error(f"WebSocket error: {e}")

    finally:
        connection_manager.disconnect(websocket)


# Periodic status broadcast task (optional - can be enabled if needed)
