# Flip-Disc

Python flip-disc display controller for Raspberry Pi. Drives flip-dot panels over RS-485 via a FastAPI server with a threaded pipeline (Generator thread -> Presenter async task).

## What This Project Does

Flip-disc displays are mechanical panels where each pixel is a small magnetic disc — one side painted (visible), one side dark. Flipping a disc requires sending a physical pulse over RS-485 serial. This project controls a grid of those panels from a Raspberry Pi.

The system has three concerns:

1. **Content** — animations produce frames (NumPy bool arrays) representing what should be displayed. Animations run continuously in a background thread, stepping forward in time and rendering grayscale frames that get binarized to 1-bit.

2. **Transport** — frames are encoded into RS-485 protocol packets and written to the serial port at the configured refresh rate. In mock mode (default) this is a no-op, so you can develop without hardware.

3. **Control** — a FastAPI server exposes HTTP endpoints and a WebSocket preview so external systems (dashboards, weather services, Home Assistant, etc.) can start/stop animations and push live updates.

### Display Hardware

The current default config (`config.toml`) is a **28×28 display** made from a 2×4 grid of 14×7 panels:
- `panel_type = "14x7"`, `columns = 2`, `rows = 4` → 28px wide × 28px tall
- `refresh_rate = 20.0` fps
- Font note: the standard font (5×7px glyphs) renders `"HELLO"` at 29px wide — 1px too wide for this display. Use the **compact font** (3×5px) or keep text short.

---

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

---

## Architecture

- `flipdisc/engine/pipeline.py` — DisplayPipeline: generator thread + async presenter, connected by `queue.Queue`
- `flipdisc/animations/` — animation classes (implement step/render_gray/configure/reset), decorator-based registry
- `flipdisc/hardware/` — RS-485 protocol encoding (spec -> formats -> protocol), panel mapping, serial transport
- `flipdisc/gfx/` — post-processing (binarize, dither, blur, sharpen, threshold)
- `flipdisc/web/` — FastAPI API server, WebSocket preview, static frontend (Web UI at `/ui`)
- `flipdisc/config.py` — TOML config loading; `DisplayConfig` derives width/height from panel grid (properties, not settable)
- `flipdisc/exceptions.py` — project-wide exception hierarchy
- `flipdisc/tests/` — pytest tests
- `assets/clips/` — pre-rendered `.npz` frame sequences + `clips.toml` manifest
- `assets/images/` — static 1-bit PNG icons for `ImageAnimation`

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
- `configure_animation(params)` — update params on the running animation in-place
- `reset()` — reset current animation state
- `get_status()` -> `PipelineStatus(running, playing, frames_presented, buffer_capacity)`
- `get_last_frame_bits()` -> last displayed frame as numpy array
- `set_preview_callback(cb)` — register callback for WebSocket preview
- `set_refresh_rate(fps)` / `reconnect_serial()` — runtime config

## Animation Interface

Subclass `Animation` and register with `@register_animation("name")`:

- `__init__(width, height)` — call `super().__init__(width, height, processing_steps=(...))`
- `step(dt)` — advance simulation by dt seconds (dt is always 1/60)
- `render_gray()` -> `np.ndarray` shape (height, width), float32 [0, 1]
- `configure(**params)` — optional, for runtime parameter changes
- `reset(seed=None)` — optional, reset to initial state

### Composed animations

`ComposedAnimation` is a base class for building multi-layer named animations. The primary pattern is to subclass it, wire up layers in `__init__` using `compose()`, and register with `@register_animation`:

```python
@register_animation("weather_dashboard")
class WeatherDashboard(ComposedAnimation):
    def __init__(self, width, height):
        super().__init__(width, height)
        temp = TextAnimation(28, 7)
        temp.configure(text="--", mode="static", font="compact")
        self.compose([(temp, {"id": "temp", "x": 0, "y": 0})])

    def configure(self, **params):
        if "temp" in params:
            self._update_layer("temp", {"text": f"{params['temp']}F"})
        super().configure(**params)
```

Start it via API: `POST /anim/weather_dashboard {"temp": 72}`

Live-update a layer without restarting: `POST /animations/configure {"layer.temp.text": "68F"}`

Layer layout keys: `id` (required), `x`, `y`, `blend` (`"over"` or `"add"`), `visible` (bool).

---

## Debugging: Terminal Frame Output

Use `print_frame` and `print_animation_frames` to render frames directly in the terminal — the fastest way to debug animation output without running the server.

```python
from flipdisc.gfx.terminal import print_frame, print_animation_frames
from flipdisc.animations.text import TextAnimation

# Inspect a single frame
anim = TextAnimation(28, 28)
anim.configure(text="HI", mode="static", font="compact")
print("error:", anim._error)        # check for silent failures
print("image:", anim._text_image)   # None = nothing will render
print_frame(anim.render_gray())

# Step through N frames
print_animation_frames(anim, n=6, dt=0.1)
```

`print_frame` outputs `█` for lit pixels and `·` for dark, so you can see exactly what would appear on the display.

**Common failure patterns to check:**

- `_text_image is None` after configure → text too wide/tall for the display (static mode silently fails); try a shorter string or the compact font
- Frame renders but looks inverted → check `processing_steps`; `binarize` at 0.5 threshold flips values ≤ 0.5 to off
- Composed animation shows nothing → check each layer individually with `print_frame(layer.anim.render_gray())`
- Clip shows nothing → `ClipAnimation._clip is None` means `configure(name=...)` wasn't called or the clip name isn't in `clips.toml`

---

## Conventions

- Ruff for linting and formatting (line-length 88, py311 target)
- Exception handling: lower layers raise typed errors with context, top-level decides severity
- `processing_steps=None` on `ClipAnimation` and `ComposedAnimation` — clips are pre-binarized; composed layers apply their own processing before blitting
- Clip fps in `clips.toml` should match the display's `refresh_rate` for correct wall-clock playback speed
