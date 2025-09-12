import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, Dict, Any

from .config import DisplayConfig
from .validation import validate_canvas_data_size

logger = logging.getLogger(__name__)


@dataclass
class Frame:
    """
    Represents a single frame in the buffer.
    """

    frame_id: int
    flags: int
    width: int
    height: int
    data: bytes
    timestamp: float

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()


class AsyncFrameBuffer:
    """
    Async frame buffer with credit system for orchestrator communication.

    Key features:
    - Maintains 0.5s buffer (15 frames at 30fps) as specified in PROJECT_CONTEXT.md
    - Credit system prevents buffer overflow and wasted computation
    - Constant frame rate display with buffer fallback
    - Thread-safe async operations
    """

    def __init__(self, display_config: DisplayConfig):
        self.config = display_config
        self.target_fps = display_config.refresh_rate
        self.frame_interval = 1.0 / self.target_fps
        self.buffer_duration = display_config.buffer_duration
        self.max_buffer_size = int(
            self.target_fps * self.buffer_duration
        )  # 15 frames at 30fps

        # Frame storage
        self._buffer = deque(maxlen=self.max_buffer_size)
        self._buffer_lock = asyncio.Lock()

        # Credit system
        self._credits = self.max_buffer_size  # Start with full credits
        self._credits_lock = asyncio.Lock()

        # Display timing
        self._last_display_time = 0.0  # monotonic seconds
        self._current_frame: Optional[Frame] = None
        self._display_running = False

        # Statistics
        self._stats = {
            "frames_received": 0,
            "frames_displayed": 0,
            "frames_dropped": 0,
            "buffer_underruns": 0,
            "credits_given": 0,
        }

        # Effective FPS measurement (rolling window)
        self._fps_window_start = time.monotonic()
        self._fps_window_count = 0
        self._fps_last = 0.0

        logger.info(
            f"Frame buffer initialized: {self.target_fps}fps, {self.buffer_duration}s buffer ({self.max_buffer_size} frames)"
        )
        logger.info(
            f"Canvas dimensions: {self.config.canvas_size.w}x{self.config.canvas_size.h}, {len(self.config.panels)} panels"
        )

    async def add_frame(self, frame: Frame) -> bool:
        """
        Add a frame to the buffer.

        Args:
            frame: Frame to add to the buffer

        Returns:
            bool: True if frame was added, False if buffer is full
        """
        async with self._buffer_lock:
            if len(self._buffer) >= self.max_buffer_size:
                self._stats["frames_dropped"] += 1
                logger.warning(f"Frame buffer full, dropping frame {frame.frame_id}")
                return False

            self._buffer.append(frame)
            self._stats["frames_received"] += 1

            logger.debug(
                f"Added frame {frame.frame_id} to buffer ({len(self._buffer)}/{self.max_buffer_size})"
            )
            return True

    async def get_next_frame(self) -> Optional[Frame]:
        """
        Get the next frame for display.
        Returns the oldest frame from buffer or None if buffer is empty.

        Returns:
            Optional[Frame]: Next frame to display, or None if buffer empty
        """
        async with self._buffer_lock:
            if self._buffer:
                frame = self._buffer.popleft()
                logger.debug(
                    f"Retrieved frame {frame.frame_id} from buffer ({len(self._buffer)} remaining)"
                )
                return frame
            else:
                self._stats["buffer_underruns"] += 1
                logger.debug("Buffer underrun - no frames available")
                return None

    async def get_current_frame(self) -> Optional[Frame]:
        """
        Get the currently displayed frame without removing it from display.

        Returns:
            Optional[Frame]: Currently displayed frame, or None
        """
        return self._current_frame

    async def peek_next_frame(self) -> Optional[Frame]:
        """
        Peek at the next frame without removing it from the buffer.

        Returns:
            Optional[Frame]: Next frame in buffer, or None if buffer empty
        """
        async with self._buffer_lock:
            return self._buffer[0] if self._buffer else None

    async def get_credits(self) -> int:
        """
        Get the current number of credits available.
        Credits represent how many frames the orchestrator can send.

        Returns:
            int: Number of credits available
        """
        async with self._credits_lock:
            return self._credits

    async def consume_credit(self) -> bool:
        """
        Consume one credit for frame production.

        Returns:
            bool: True if credit was consumed, False if no credits available
        """
        async with self._credits_lock:
            if self._credits > 0:
                self._credits -= 1
                logger.debug(f"Credit consumed, {self._credits} remaining")
                return True
            return False

    async def add_credits(self, count: int) -> None:
        """
        Add credits back to the system (called when frames are displayed).

        Args:
            count: Number of credits to add
        """
        async with self._credits_lock:
            old_credits = self._credits
            self._credits = min(self._credits + count, self.max_buffer_size)
            added = self._credits - old_credits

            if added > 0:
                self._stats["credits_given"] += added
                logger.debug(
                    f"Added {added} credits, total: {self._credits}/{self.max_buffer_size}"
                )

    async def display_frame_at_rate(self) -> Optional[Frame]:
        """
        Get frame for display according to target frame rate.
        This method enforces constant frame rate timing.

        Returns:
            Optional[Frame]: Frame to display, or current frame if no new frame ready
        """
        current_time = time.monotonic()

        # Check if it's time for the next frame
        if current_time - self._last_display_time >= self.frame_interval:
            # Try to get a new frame
            new_frame = await self.get_next_frame()

            if new_frame:
                self._current_frame = new_frame
                self._last_display_time = current_time
                self._stats["frames_displayed"] += 1

                # Update FPS window
                self._fps_window_count += 1
                elapsed = current_time - self._fps_window_start
                if elapsed >= 1.0:
                    self._fps_last = self._fps_window_count / elapsed
                    self._fps_window_start = current_time
                    self._fps_window_count = 0

                # Give back a credit since we consumed a frame
                await self.add_credits(1)

                logger.debug(
                    f"Displaying new frame {new_frame.frame_id} at {current_time:.3f}s"
                )
                return new_frame
            else:
                # No new frame available, return current frame (buffer fallback)
                logger.debug("No new frame available, using current frame")
                return self._current_frame
        else:
            # Not time for next frame yet
            return None

    async def clear_buffer(self) -> int:
        """
        Clear all frames from the buffer.

        Returns:
            int: Number of frames cleared
        """
        async with self._buffer_lock:
            count = len(self._buffer)
            self._buffer.clear()

            # Reset credits to maximum
            async with self._credits_lock:
                self._credits = self.max_buffer_size

            logger.info(
                f"Cleared {count} frames from buffer, reset credits to {self.max_buffer_size}"
            )
            return count

    def get_buffer_status(self) -> Dict[str, Any]:
        """
        Get current buffer status and statistics.

        Returns:
            Dict: Buffer status information
        """
        return {
            "buffer_size": len(self._buffer),
            "max_buffer_size": self.max_buffer_size,
            "buffer_utilization": len(self._buffer) / self.max_buffer_size,
            "credits_available": self._credits,
            "target_fps": self.target_fps,
            "fps_actual": self._fps_last,
            "frame_interval": self.frame_interval,
            "current_frame_id": (
                self._current_frame.frame_id if self._current_frame else None
            ),
            "stats": self._stats.copy(),
        }

    def update_target_fps(self, fps: float) -> None:
        if fps <= 0:
            raise ValueError("FPS must be > 0")
        self.target_fps = fps
        self.frame_interval = 1.0 / fps
        # reset pacing window to avoid a long catch-up
        self._last_display_time = 0.0

    def get_buffer_health(self) -> Dict[str, Any]:
        """
        Get buffer health metrics for monitoring.

        Returns:
            Dict: Health metrics
        """
        buffer_level = len(self._buffer) / self.max_buffer_size

        # Determine health status
        if buffer_level > 0.8:
            health = "excellent"
        elif buffer_level > 0.5:
            health = "good"
        elif buffer_level > 0.2:
            health = "fair"
        elif buffer_level > 0:
            health = "poor"
        else:
            health = "critical"

        return {
            "health": health,
            "buffer_level": buffer_level,
            "underrun_rate": self._stats["buffer_underruns"]
            / max(self._stats["frames_displayed"], 1),
            "drop_rate": self._stats["frames_dropped"]
            / max(self._stats["frames_received"], 1),
            "credits_ratio": self._credits / self.max_buffer_size,
        }

    async def start_display_loop(self, display_callback) -> None:
        """
        Start the async display loop that calls display_callback at target frame rate.

        Args:
            display_callback: Async function to call with each frame for display
        """
        if self._display_running:
            logger.warning("Display loop already running")
            return

        self._display_running = True
        logger.info(f"Starting display loop at {self.target_fps}fps")

        try:
            while self._display_running:
                frame = await self.display_frame_at_rate()

                if frame:
                    try:
                        await display_callback(frame)
                    except Exception as e:
                        logger.error(f"Error in display callback: {e}")

                # Sleep until next frame time
                await asyncio.sleep(
                    self.frame_interval / 4
                )  # Check 4x per frame interval

        except asyncio.CancelledError:
            logger.info("Display loop cancelled")
        finally:
            self._display_running = False
            logger.info("Display loop stopped")

    async def stop_display_loop(self) -> None:
        """
        Stop the display loop.
        """
        self._display_running = False
        logger.info("Stopping display loop")


def create_frame_for_canvas(
    frame_id: int, canvas_data: bytes, display_config: DisplayConfig, flags: int = 0
) -> Frame:
    """
    Create a Frame object for a full canvas bitmap.

    Args:
        frame_id: Unique frame identifier
        canvas_data: Packed bitmap data for the entire canvas
        display_config: Display configuration for dimensions
        flags: Frame flags (bit 0 = invert, bits 1-7 reserved)

    Returns:
        Frame: Frame object ready for buffer
    """
    canvas_w = display_config.canvas_size.w
    canvas_h = display_config.canvas_size.h

    validate_canvas_data_size(len(canvas_data), canvas_w, canvas_h)

    return Frame(
        frame_id=frame_id,
        flags=flags,
        width=canvas_w,
        height=canvas_h,
        data=canvas_data,
        timestamp=time.time(),
    )


def validate_frame_for_display(frame: Frame, display_config: DisplayConfig) -> bool:
    """
    Validate that a frame matches the display configuration.

    Args:
        frame: Frame to validate
        display_config: Display configuration

    Returns:
        bool: True if frame is valid for the display
    """
    expected_w = display_config.canvas_size.w
    expected_h = display_config.canvas_size.h

    if frame.width != expected_w or frame.height != expected_h:
        logger.warning(
            f"Frame {frame.frame_id} dimensions {frame.width}x{frame.height} don't match display {expected_w}x{expected_h}"
        )
        return False

    expected_bytes = expected_h * ((expected_w + 7) // 8)
    if len(frame.data) != expected_bytes:
        logger.warning(
            f"Frame {frame.frame_id} data size {len(frame.data)} doesn't match expected {expected_bytes}"
        )
        return False

    return True
