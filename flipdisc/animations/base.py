"""Base animation interface for flip-disc displays."""

import time
from abc import ABC, abstractmethod
from typing import Any, Literal

import numpy as np

from flipdisc.core.exceptions import AnimationError

OutputFormat = Literal["gray", "binary"]


class Animation(ABC):
    """
    Base class for all flip-disc animations.

    This matches the interface from your outline:
    - step(dt) advances the simulation
    - render_gray() returns grayscale frame
    - configure() sets animation parameters
    - reset() resets animation state
    - output_format declares whether animation outputs "gray" or "binary"
    """

    def __init__(self, width: int, height: int,
                 output_format: OutputFormat = "gray",
                 processing_steps: tuple[str, ...] | None = ("binarize",)):
        if width <= 0 or height <= 0:
            raise AnimationError(
                f"Animation dimensions must be positive: {width}x{height}"
            )

        self.width = width
        self.height = height
        self.output_format = output_format
        self.processing_steps = processing_steps
        self.start_time = time.time()
        self.current_time = 0.0
        self.params: dict[str, Any] = {}

    @abstractmethod
    def step(self, dt: float) -> None:
        """
        Advance the animation simulation by dt seconds.

        Args:
            dt: Time step in seconds (typically 1/60 for 60fps)
        """

    @abstractmethod
    def render_gray(self) -> np.ndarray:
        """
        Render current animation state to grayscale image.

        Returns:
            Grayscale image as float array (0.0 to 1.0)
            Shape should be (height, width)
        """

    def configure(self, **params: Any) -> None:
        """
        Configure animation parameters.

        Args:
            **params: Animation-specific parameters
        """
        self.params.update(params)

    def reset(self, seed: int | None = None) -> None:
        """
        Reset animation to initial state.

        Args:
            seed: Optional random seed for deterministic behavior
        """
        self.start_time = time.time()
        self.current_time = 0.0
        if seed is not None:
            np.random.seed(seed)

    def get_info(self) -> dict[str, Any]:
        """Get animation info and current parameters."""
        return {
            "name": self.__class__.__name__.lower(),
            "dimensions": (self.width, self.height),
            "current_time": self.current_time,
            "params": self.params.copy(),
        }


# Animation registry for worker processes
_ANIMATION_REGISTRY: dict[str, type] = {}


def register_animation(name: str):
    """Decorator to register an animation class."""

    def decorator(cls):
        if not issubclass(cls, Animation):
            raise AnimationError(f"Registered class must inherit from Animation: {cls}")
        _ANIMATION_REGISTRY[name] = cls
        return cls

    return decorator


def get_animation(name: str, width: int, height: int) -> Animation:
    """
    Factory function to create animation instances.

    Args:
        name: Animation name
        width: Display width
        height: Display height

    Returns:
        Animation instance

    Raises:
        AnimationError: If animation not found
    """
    if name not in _ANIMATION_REGISTRY:
        raise AnimationError(
            f"Unknown animation: {name}. Available: {list(_ANIMATION_REGISTRY.keys())}"
        )

    animation_class = _ANIMATION_REGISTRY[name]
    try:
        return animation_class(width, height)
    except Exception as e:
        raise AnimationError(f"Failed to create animation '{name}': {e}") from e


def list_animations() -> list[str]:
    """Get list of available animation names."""
    return list(_ANIMATION_REGISTRY.keys())
