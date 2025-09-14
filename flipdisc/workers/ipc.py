"""Lightweight IPC types for animation workers.

We send Python dataclass objects through multiprocessing.Queue, avoiding
custom wire formats for the single-Pi, single-host case.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class Command:
    """Base class for worker commands."""

    cmd: str


@dataclass
class CreditCommand(Command):
    """Signal to worker to generate one frame."""

    cmd: str = "credit"


@dataclass
class SetAnimationCommand(Command):
    """Change current animation."""

    cmd: str = "set_anim"
    name: str = ""
    params: dict[str, Any] = None

    def __post_init__(self):
        if self.params is None:
            self.params = {}


@dataclass
class ResetCommand(Command):
    """Reset current animation state."""

    cmd: str = "reset"
    seed: int | None = None


@dataclass
class ConfigureCommand(Command):
    """Configure current animation parameters."""

    cmd: str = "configure"
    params: dict[str, Any] = None

    def __post_init__(self):
        if self.params is None:
            self.params = {}


@dataclass
class TestPatternCommand(Command):
    """Generate a test pattern."""

    cmd: str = "test_pattern"
    pattern: str = "checkerboard"


@dataclass
class ShutdownCommand(Command):
    """Shutdown worker process."""

    cmd: str = "shutdown"


@dataclass
class Response:
    """Worker response message."""

    success: bool
    frame: Any | None = None  # numpy.ndarray[bool] or None
    error: str | None = None
    info: dict[str, Any] | None = None
    # When sent through Queue, this object is pickled.
