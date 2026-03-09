"""Clip loader for pre-rendered .npz frame sequences."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_CLIPS_CONFIG = "assets/clips/clips.toml"

_clip_cache: dict[str, "ClipData"] = {}


@dataclass
class ClipData:
    """Pre-rendered frame sequence loaded from a .npz file."""

    frames: np.ndarray  # (N, H, W) bool
    fps: float
    loop: bool
    width: int
    height: int
    description: str


def load_clip(name: str, config_path: str = _CLIPS_CONFIG) -> ClipData:
    """Load a named clip from the clips TOML config.

    Args:
        name: Clip name as defined in the TOML.
        config_path: Path to clips.toml, relative to the project root.

    Returns:
        A ClipData instance (cached after first load).
    """
    cache_key = f"{config_path}:{name}"
    if cache_key in _clip_cache:
        return _clip_cache[cache_key]

    with Path(config_path).open("rb") as f:
        config = tomllib.load(f)

    if name not in config:
        raise KeyError(f"Clip '{name}' not found in {config_path}")

    entry = config[name]
    data = np.load(entry["path"])
    frames = data["frames"].astype(bool)

    clip = ClipData(
        frames=frames,
        fps=float(entry.get("fps", 20.0)),
        loop=bool(entry.get("loop", True)),
        width=int(entry.get("width", frames.shape[2])),
        height=int(entry.get("height", frames.shape[1])),
        description=str(entry.get("description", "")),
    )

    _clip_cache[cache_key] = clip
    return clip


def list_clips(config_path: str = _CLIPS_CONFIG) -> list[str]:
    """Return names of all clips defined in the manifest."""
    with Path(config_path).open("rb") as f:
        config = tomllib.load(f)
    return list(config.keys())
