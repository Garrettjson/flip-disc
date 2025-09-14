# Flip-Disc (Python, single-Pi)

A fast, robust flip-dot display controller written 100% in Python. It runs on a single Raspberry Pi (or any Linux box), exposes a FastAPI HTTP interface, spawns one or more animation worker processes, and drives flip-dot panels over RS-485 with a small, protocol-correct encoder.

Highlights
- Async hardware ticker that paces the display (default 20 FPS) and owns serial I/O
- Backpressure with credit-based workers (server “pulls” frames); ~0.5s buffer for smoothness
- Multiprocessing animation workers generate grayscale, dither to binary (bool), and return images
- Segmented panel writes + proper flush semantics (7x7 immediate refresh; 14x7/28x7 buffered + flush)
- Clean separation: engine (runtime components), hardware (protocol/transport), animations (step/render), workers (IPC), core (types)


## Quick Start

Requirements
- Python 3.11+
- `uv`

Install (dev) with uv:
```bash
# Install dependencies (including dev extras) using the lockfile
uv sync --extra dev

# Optionally, activate the created virtualenv (uv creates .venv by default)
source .venv/bin/activate
```

Run the server (mock serial by default):
```bash
python -m flipdisc run-server --config config.toml --workers 1 --host 0.0.0.0 --port 8000
```

Endpoints @`http://localhost:8000`:
- [Status](http://localhost:8000/status): `/status`
- [API Docs](http://localhost:8000/docs): `/docs`
- [List animations](http://localhost:8000/animations): `/animations`
- [Start animation](http://localhost:8000/anim/bouncing_dot): `/anim/bouncing_dot`(POST)
- [Set refresh rate](http://localhost:8000/fps?new_fps=15): `/fps?new_fps=15` (POST)
- [Send test pattern](http://localhost:8000/display/test/checkerboard): `/test/checkerboard` (POST)
- [Web UI](http://localhost:8000/ui): `/ui` (static page served by FastAPI)



## Configuration (config.toml)

Minimum example (works with mock serial):
```toml
[display]
# Panel grid (each panel is 14x7); default canvas = 28x28
panel_type = "14x7"     # "7x7", "14x7", or "28x7"
columns = 2              # horizontal panel count (14*2 = 28)
rows = 4                 # vertical panel count (7*4 = 28)
refresh_rate = 20.0      # frames per second paced by the server
buffer_duration = 0.5    # seconds of frames the buffer can hold
# Optional base address for the first panel (panels are addressed row-major)
address_base = 1

[serial]
# Serial transport. Use mock=true for development.
port = "/dev/ttyUSB0"
baudrate = 9600
timeout = 1.0
mock = true
```

Notes
- Width = panel_w * columns, height = panel_h * rows. With 14x7 x 2x4 -> 28x28.
- 7x7 panels do not support buffered refresh; the controller sends immediate-refresh messages without a flush.
- 14x7 and 28x7 are sent as buffered messages, then a broadcast flush is issued.
- address_base sets the starting panel address and increments per panel in row-major order.


## Project Layout (ascii)

```
flip-disc/
├─ app.py                     # Wrapper: runs flipdisc.app:main()
├─ config.toml                # Example configuration (TOML)
├─ pyproject.toml             # Package + tooling (ruff, pytest)
├─ README.md
└─ flipdisc/
   ├─ __main__.py             # `python -m flipdisc`
   ├─ __init__.py
   ├─ app.py                  # Orchestrates engine lifecycle
   ├─ cli.py                  # Small CLI: run-server
   ├─ logging_conf.py
   ├─ config.py               # Config loading + validation (TOML)
   ├─ core/
   │  ├─ types.py             # Frame dataclass
   │  └─ exceptions.py        # Project-wide exceptions
   ├─ engine/                 # Long-lived runtime components
   │  ├─ api_server.py        # FastAPI endpoints
   │  ├─ display_pacer.py     # Pacing, buffer, serial writes, credits
   │  └─ worker_pool.py       # Spawns workers, issues credits, enqueues frames
   ├─ workers/
   │  ├─ ipc.py               # Simple dataclasses for IPC
   │  └─ runner.py            # Worker loop (step -> render_gray -> dither -> bool)
   ├─ anims/
   │  ├─ base.py              # Animation interface (step/render_gray/config/reset)
   │  ├─ bouncing_dot.py
   │  ├─ life.py
   │  └─ pendulum.py
   ├─ hardware/
   │  ├─ protocol/
   │  │  ├─ spec.py           # Protocol enums + command map
   │  │  └─ formats.py        # Encoder (panel msgs + flush)
   │  ├─ panel_map.py         # Slice canvas to per-panel bitmaps
   │  └─ transport/
   │     └─ serial.py         # Serial transports (hardware/mock)
   ├─ gfx/
   │  └─ dither.py            # Ordered Bayer, error diffusion, threshold
   └─ tests/
      ├─ test_basic.py        # Basic hardware/anim/worker assertions
      ├─ test_formats.py      # Golden tests for formats/packing
      └─ test_pacing.py       # Pacing smoke test with MockSerial
```


## Control Flow

```mermaid
sequenceDiagram
    autonumber
    participant API as ApiServer
    participant WM as WorkerPool
    participant W as Worker (proc)
    participant HW as DisplayPacer
    participant SP as SerialTransport
    participant P as Panels

    API->>WM: POST /anim/{name}
    WM->>W: SetAnimationCommand(name)
    Note over HW: Ticker @ refresh_rate
    loop Every tick
        HW->>HW: free = buffer.free()
        alt free > 0
            HW->>WM: credit_callback(count=free)
            WM->>W: CreditCommand x free (round-robin)
            W->>WM: Response(frame=bool[HxW])
            WM->>HW: enqueue Frame(bits, seq, produced_ts)
        end
        HW->>SP: encode panels + write (batch)
        alt panels 7x7
            Note over HW,SP: Refresh=true per panel; no flush
        else 14x7/28x7
            SP-->>P: write frames
            SP->>P: broadcast flush
        end
    end
```


## Development

Run tests:
```bash
uv run pytest -q
```

Lint + format:
```bash
uv run ruff format
uv run ruff check --fix
```

Tips
- The app uses the multiprocessing "spawn" start method for parity across macOS/Linux.
- Exception handling follows "log at level of knowledge": lower layers raise typed errors with context; top-level decides severity.
- Mock serial is on by default; set `mock=false` to write to real hardware.


## API (selected)

- GET `/status`: hardware (buffer, free, drops, frames_presented) + workers (frames collected/dropped)
- GET `/animations` -> { animations }
- POST `/anim/{name}` -> start animation
- POST `/animations/configure` -> set params on current animation
- POST `/animations/reset`
- GET `/fps` -> { refresh_rate }
- POST `/fps?new_fps=20` -> update refresh rate atomically
- POST `/display/test/{pattern}` -> checkerboard | solid | clear
- POST `/serial/reconnect`
- POST `/workers/restart`
