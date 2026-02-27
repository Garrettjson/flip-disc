# Flip-Disc

Python flip-disc display controller for Raspberry Pi. Drives flip-dot panels over RS-485 via a FastAPI server with a threaded pipeline (Generator thread -> Presenter async task).

## Setup

- Python 3.11+, uses `uv` for dependency management
- Install: `uv sync --extra dev`
- Run server: `uv run python -m flipdisc run-server --config config.toml --host 0.0.0.0 --port 8000`
- Mock serial is on by default (`mock = true` in config.toml)

## Dev Commands

- Test: `uv run pytest -q`
- Lint: `uv run ruff check --fix`
- Format: `uv run ruff format`
- Dev server (hot reload): `uv run python -m flipdisc run-server --reload`

## Architecture

- `flipdisc/engine/pipeline.py` — DisplayPipeline: generator thread + async presenter, connected by `queue.Queue`
- `flipdisc/animations/` — animation classes (implement step/render_gray/configure/reset), decorator-based registry
- `flipdisc/hardware/` — RS-485 protocol encoding (spec -> formats -> protocol), panel mapping, serial transport
- `flipdisc/gfx/` — post-processing (binarize, dither, blur, sharpen, threshold)
- `flipdisc/web/` — FastAPI API server, WebSocket preview, static frontend (Web UI at `/ui`)
- `flipdisc/config.py` — TOML config loading; `DisplayConfig` derives width/height from panel grid (properties, not settable)
- `flipdisc/exceptions.py` — project-wide exception hierarchy
- `flipdisc/tests/` — pytest tests

## Pipeline Design

- **Generator thread** runs animations in a background `threading.Thread`, stepping the simulation, applying post-processing, and pushing frames into a `queue.Queue(maxsize=N)`
- **Presenter** is an async task that pulls frames at `refresh_rate`, encodes them for the hardware, writes to serial, and broadcasts preview frames
- **Frame buffer** (`queue.Queue`) smooths compute spikes — the generator stays ahead, keeping the buffer full, so the presenter always has frames to display
- **Animation switching** is a simple reference swap: main thread sets `_anim_request`, generator thread picks it up, drains the queue, and creates the new animation
- **Backpressure**: generator blocks on `queue.put(timeout=0.05)` when the buffer is full — natural flow control
- NumPy releases the GIL during array operations, so the thread gives real concurrency for compute-heavy animations

## DisplayPipeline Public API

All methods are async except `get_status()`, `get_last_frame_bits()`, and `set_preview_callback()`:

- `start(animation, params)` / `stop()` — lifecycle
- `play()` / `pause()` — playback control
- `set_animation(name, params)` — switch animation (no restart needed)
- `reset()` — reset current animation state
- `get_status()` -> `PipelineStatus(running, playing, frames_presented, buffer_capacity)`
- `get_last_frame_bits()` -> last displayed frame as numpy array
- `set_preview_callback(cb)` — register callback for WebSocket preview
- `set_refresh_rate(fps)` / `reconnect_serial()` — runtime config

## Animation Interface

Subclass `Animation` and register with `@register_animation("name")`:

- `__init__(width, height)` — call `super().__init__(width, height, processing_steps=(...))`
- `step(dt)` — advance simulation by dt seconds
- `render_gray()` -> `np.ndarray` shape (height, width), float32 [0, 1]
- `configure(**params)` — optional, for runtime parameter changes
- `reset(seed=None)` — optional, reset to initial state

## Conventions

- Ruff for linting and formatting (line-length 88, py311 target)
- Exception handling: lower layers raise typed errors with context, top-level decides severity
