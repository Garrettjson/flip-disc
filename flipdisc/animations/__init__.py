"""Animation module for flip-disc displays."""

# Import all animations to register them
from . import bouncing_dot, clip, composed, image, life, pendulum, simplex_noise, text, wireframe_cube
from .base import Animation, get_animation, list_animations, register_animation

__all__ = [
    "Animation",
    "bouncing_dot",
    "clip",
    "composed",
    "get_animation",
    "image",
    "life",
    "list_animations",
    "pendulum",
    "register_animation",
    "simplex_noise",
    "text",
    "wireframe_cube",
]
