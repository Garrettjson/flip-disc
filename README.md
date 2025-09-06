# Flip‑Disc — End‑to‑End Flip‑Dot Display Stack

This repo contains a complete pipeline to drive a physical flip‑disc (flip‑dot) display: content workers generate frames, an orchestrator selects an active source, and a server attached to the RS‑485 bus handles mapping, pacing, and output. A built‑in viewer and stats endpoints make development fast without hardware.

**At a glance**
- Server: Python FastAPI app (RS‑485 writer, ring buffer, FPS pacing, viewer)
- Orchestrator: Minimal Node service to accept worker frames and forward the active source
- Workers: Python processes (example: bouncing dot) that post RBM frames
- Protocol: RBM (Raw Bitmap), 1‑bit packed canvas with a small big‑endian header


**Overview**
- Render text/graphics/video to flip‑discs with smooth timing and predictable behavior.
- Keep the hardware controller simple and deterministic next to the serial bus (on a Pi).
- Allow rich content generation from other machines; add a web UI later.
- Maintain a small server‑side buffer so timing is stable despite network jitter.


**Architecture**
- Server (`server/`)
  - Owns the RS‑485 serial line, authoritative frame buffer, and pacing.
  - Accepts frames via HTTP (`POST /ingest/rbm`) in RBM format.
  - Maps a virtual canvas to physical panels (orientation, tiling) via NumPy.
  - Enforces FPS and inter‑frame gap; optional inter‑panel serial delay.
  - Serves a PNG viewer (`/frame.png`) and per‑panel previews (`/debug/panel.png`).
  - Exposes config (`/config`) and runtime stats (`/stats`).
- Orchestrator (`orchestrator/`)
  - Accepts RBM frames from workers at `/workers/:id/frame`.
  - Tracks an active source (`POST /active`) and forwards frames to the server.
  - Proxies `/config` to the server for clients.
  - UI includes a "Video Feed" that proxies `/frame.png` from the server (live output). The preview scale is adjustable in the UI.
- Workers (`workers/`)
  - One process per content stream; draw in the virtual canvas and post frames.
  - Python workers can subclass `WorkerBase` (in `workers/common/base.py`) which handles config, preview, RBM packing, and posting.
  - Examples: `workers/bouncing_dot/` and `workers/text_scroll/` both use the common base.

Why this split
- Deterministic output: the server buffers and paces locally at the hardware edge.
- Performance & ergonomics: Python for image/CV work, Node for orchestration/UI.
- Scalability: multiple workers; orchestrator can switch or mix sources.


**Protocol — RBM (Raw Bitmap)**
- Header (16 bytes, big‑endian): `magic="RB"`, `version=1`, `flags`, `width`, `height`, `seq`, `frame_duration_ms`, `reserved`.
- Payload: `height * ceil(width/8)` bytes, row‑major, MSB‑first per byte.
- Sequence wraps at 2^32; `frame_duration_ms=0` uses server FPS.
- Spec: `protocol/rbm_spec.md:1`.


**Configuration**
- Display topology lives in `config/display.yaml:1`.
  - `canvas: { width, height }`
  - `fps: 30` (target refresh rate)
  - `panel_size: { width, height }`
  - `panels: [{ id, address, origin: {x,y}, size: {w,h}, orientation }]`
  - `serial: { device, baud, parity, data_bits, stop_bits }`

**Hardware Panels**
- The display is two sub-displays (panels), each 7×28 pixels, stacked to form a 14×28 canvas.
- Each panel has its own RS‑485 address; the bus is wired in parallel.
- Hardware requires sending a full panel frame when any pixel in that panel changes.

Panel layout (Y increases downward):

  Columns → 0 ……………………………… 27
  Rows
    0  +----------------------------+   ← top panel (id: "top", 7×28)
    1  |                            |
    2  |          TOP (7×28)        |
    3  |                            |
    4  |                            |
    5  |                            |
    6  +----------------------------+
    7  +----------------------------+   ← bottom panel (id: "bottom", 7×28)
    8  |                            |
    9  |        BOTTOM (7×28)       |
   10  |                            |
   11  |                            |
   12  |                            |
   13  +----------------------------+

What the server does today:
- Treats the whole 14×28 as a virtual canvas, then derives per-panel bitmaps every tick.
- Sends a full RS‑485 message per panel each tick: `[0x80][cfg][addr][28 data bytes][0x8F]`.
- This guarantees correctness for all animations and simplifies pacing.

Future optimization (panel‑dirty):
- Detect if a panel’s bytes are unchanged from the last tick and skip the RS‑485 write for that panel. This halves bus traffic for content localized to one panel.
- “Dirty‑rects” at panel granularity: instead of arbitrary rectangles, we update at panel‑tile resolution (7×28) to match hardware behavior.


**Getting Started**

One‑time setup
- Install uv (fast Python package manager and runner):
  - macOS: `brew install uv`
  - Cross‑platform: `curl -Ls https://astral.sh/uv/install.sh | sh`
- Initialize the server environment and deps:
  - `make uv-setup`
 - Initialize the workers environment and deps (separate venv):
   - `make uv-setup-workers`

Project workflow (auto‑managed workers)
- Start server: `make run-server` (viewer at `http://localhost:8080/`)
- Start orchestrator (first time `make bun-setup`): `make run-orchestrator`
- Set active worker (orchestrator starts/stops workers):
  - UI: `http://localhost:8090/` → choose worker → “Set Active”, or
  - `curl -XPOST localhost:8090/active -H 'Content-Type: application/json' -d '{"id":"bouncing-dot"}'`
- Optional: override orchestrator FPS:
  - `curl -XPOST localhost:8090/fps -H 'Content-Type: application/json' -d '{"fps":20}'`
  - Clear override: `curl -XDELETE localhost:8090/fps`
- Single activation control: Use the top‑level “Set Active” and “Stop Active” buttons. Per‑worker sections (e.g., Text Scroll) expose config only (no separate activate button).
- Manual worker control: `POST /workers/:id/start` and `POST /workers/:id/stop`
- Update deps when `server/pyproject.toml` changes:
  - `make uv-sync` (optional `make uv-lock` to commit `server/uv.lock`)
 - Update deps when `workers/pyproject.toml` changes:
  - `make uv-sync-workers` (optional `make uv-lock-workers`)


**Bouncing Dot Demo**
- Start the server and orchestrator (as above), then set `/active` to `bouncing-dot`.
- The orchestrator will spawn the worker; open the viewer and you should see the dot animating.
- Optional: to bypass the orchestrator, run the worker manually with `TARGET_URL=http://localhost:8080/ingest/rbm`.

Stop the active worker
- From the UI, click “Stop Active”, or via API: `curl -XPOST localhost:8090/active -H 'Content-Type: application/json' -d '{"id":null}'`.

Restart the active worker
- From the UI, click “Restart Active”, or via API sequence:
  - `curl -XPOST localhost:8090/workers/<id>/stop`
  - `curl -XPOST localhost:8090/workers/<id>/start`
  
Preview scale
- In the UI’s Server section, adjust the numeric Scale control (1–64). The preview image uses this scale when fetching `/frame.png`.

Worker config via orchestrator
- Workers poll `GET /workers/:id/config` ~1 Hz; you can update settings via the UI or `curl`:
  - `curl -XPOST localhost:8090/workers/text-scroll/config -H 'Content-Type: application/json' -d '{"text":"HELLO","pps":12,"letter_spacing":1}'`


**Server Flags (CLI after `--`)**
- `--config config/display.yaml`
- `--fps 30` (overrides config)
- `--buffer_ms 1000` (~1s ring buffer)
- `--frame_gap_ms N` (min gap after each frame)
- `--serial` (enable RS‑485)
- `--serial_device /dev/ttyUSB0`, `--serial_baud 115200`
- `--serial_parity none|even|odd`, `--serial_databits 8`, `--serial_stopbits 1`
- `--serial_interpanel_us N` (microseconds between panel packets)


**Endpoints**
- Server: `POST /ingest/rbm`, `GET /frame.png?scale=10`, `GET /debug/panel.png?id=top&scale=20`, `GET /config`, `GET /stats`, `GET /healthz`.
- Orchestrator: `POST /workers/:id/frame`, `POST /active`, `GET /active`, `GET /stats`, `GET /config`, `GET /healthz`.
  - Worker config endpoints (orchestrator): `GET/POST /workers/:id/config` (used by text-scroll worker for text/speed).
  - Ingest validation: RBM header magic/version are checked; frames are rejected if `width/height` don’t match the server canvas.
  - Proxy: `GET /frame.png` forwards to server `/frame.png` for the UI preview.

Worker process management (orchestrator)
- `POST /workers/:id/start` and `POST /workers/:id/stop`
- `POST /active {"id": "<worker-id>"}` to switch and auto start; `{"id": null}` to stop current.
- `/stats` and `/active` include `running` list.

**Troubleshooting**
- “Multiple top-level packages discovered” during `uv sync` in `workers/`:
  - Fixed by declaring no packages in `workers/pyproject.toml` (`tool.setuptools.packages = []`). Run `make uv-setup-workers` again.
- Worker doesn’t auto-start when setting `/active`:
  - Ensure `uv` is installed and on PATH; run `uv --version`. If missing, install per “One-time setup”.
  - Ensure `make uv-setup-workers` was run to create the workers’ venv.
  - Check orchestrator logs for spawn errors.
- RBM size mismatch errors in UI (“size mismatch: got WxH want …”):
  - Make sure the worker is using `WorkerBase` and not hardcoding sizes. Workers fetch canvas size from `/config`.
- Viewer doesn’t update:
  - Confirm server is running on `:8080` and orchestrator on `:8090`.
  - Check server `/stats`; verify `frames_received` is increasing.
- Tk preview window issues (local dev):
  - Workers run with `HEADLESS=1` when spawned by orchestrator. Run workers manually if you want the Tk preview.
- Bun not installed:
  - Install with `brew install bun` (macOS) or follow https://bun.sh. Then `make bun-setup`.


**Implementation Details**
- Mapping & rendering: Vectorized NumPy (no fallbacks). Orientation with `np.rot90/flip`, packing via `np.packbits`, viewer via `np.kron` upscaling.
- Serial writer: Uses `aioserial` for non‑blocking writes. Per‑panel delay and inter‑frame gap supported.
- Pacing: Ring buffer with “keep latest” behavior; FPS enforced even if frames arrive faster.
- JSON: `orjson` response class; event loop uses `uvloop` where supported.

See also: `next-steps.md` for protocol evolution (XOR/dirty‑rects), orchestrator pacing options, and server optimizations.


**Repo Map**
- `server/`: Python server (FastAPI app in `server/api.py`, engine in `server/engine.py`).
- `orchestrator/`: Minimal Node service.
- `workers/`: Workers, common harness (`workers/common/base.py`), RBM helpers, separate venv with `workers/pyproject.toml`.
- `config/display.yaml`: Topology and serial settings.
- `protocol/rbm_spec.md`: Wire format spec.
- `MONOREPO.md`: Additional run notes and flags.

**VS Code (Multi‑Root Workspace + Pylance)**
- Open the workspace file `flip-disc.code-workspace` to edit `server/` and `workers/` as separate roots.
- Set interpreter per root (Command Palette → “Python: Select Interpreter”):
  - Server: `${workspaceFolder}/.venv/bin/python`
  - Workers: `${workspaceFolder}/.venv/bin/python`
- Optional local settings (not committed; `.gitignore` excludes `.vscode/`):
  - `server/.vscode/settings.json`
    - `{ "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python", "python.analysis.extraPaths": ["${workspaceFolder}/.."] }`
  - `workers/.vscode/settings.json`
    - `{ "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python", "python.analysis.extraPaths": ["${workspaceFolder}/.."] }`
  - On Windows, the interpreter path is `"${workspaceFolder}\\.venv\\Scripts\\python.exe"`.


**Next Steps**
- Add systemd unit and env files for running on a Pi via uv.
- Add optional metrics exporter (Prometheus) and richer viewer controls.
- Expand tests with golden RBM vectors and mapping parity checks.

**Raspberry Pi (systemd) Deployment**
- See `deploy/README-systemd.md` for step‑by‑step instructions.
- Env files (edit under `/etc/flipdisc/`):
  - `server.env`: `PORT`, `FLIPDISC_SERIAL=1`, `FLIPDISC_SERIAL_DEVICE`, `FLIPDISC_FPS`, etc.
  - `orchestrator.env`: `PORT`, `SERVER_URL`
  - `worker-<id>.env`: per‑worker env (e.g., `worker-text-scroll.env`, `worker-bouncing-dot.env`). Samples in `deploy/env/`.
- Units installed to `/etc/systemd/system/`:
  - `flipdisc-server.service` (uv/uvicorn FastAPI server)
  - `flipdisc-orchestrator.service` (Bun server)
  - `flipdisc-worker@.service` (templated Python worker; run instances like `flipdisc-worker@text-scroll`)

Quick worker instance usage
- Copy and edit a worker env sample:
  - `sudo cp deploy/env/worker-text-scroll.env.sample /etc/flipdisc/worker-text-scroll.env`
  - `sudo nano /etc/flipdisc/worker-text-scroll.env`
- Start and enable the worker instance:
  - `sudo systemctl enable --now flipdisc-worker@text-scroll`
- Logs for a single worker:
  - `journalctl -u flipdisc-worker@text-scroll -f`

Installer options
- The installer can auto‑enable worker instances:
  - Explicit list: `sudo WORKERS="text-scroll bouncing-dot" bash deploy/install_systemd.sh`
  - Enable all with env files: `sudo AUTO_ENABLE_WORKERS=1 bash deploy/install_systemd.sh`


**Worker SDK (Python)**
- Base harness: `workers/common/base.py` exposes `WorkerBase` and `DisplayInfo`.
- Implement: `render(t: float, display: DisplayInfo, cfg: dict) -> Iterable[Iterable[int]]` returning a 2D 0/1 frame sized to the canvas.
- Harness handles:
  - Fetch display size/FPS via orchestrator `GET /config` (proxied from server).
  - Poll per‑worker config via `GET /workers/:id/config` (~1 Hz).
  - Enforce frame shape (default strict; optional `size_policy="pad"`).
  - Local preview window (Tk or no‑op with `HEADLESS=1`).
  - RBM packing and `POST /workers/:id/frame`.
- Env vars: `ORCH_URL` (default `http://localhost:8090`), optional `TARGET_URL` to post directly to the server, `HEADLESS=1` to disable preview.
  - When orchestrator spawns workers, it sets `HEADLESS=1` so no Tk window opens. When you run a worker manually (CLI), omit `HEADLESS` to see the Tk preview (if Tk is installed).

Minimal example
```
from typing import Iterable, List
from workers.common.base import WorkerBase, DisplayInfo

class Example(WorkerBase):
    def __init__(self):
        super().__init__("example")

    def render(self, t: float, display: DisplayInfo, cfg: dict) -> Iterable[Iterable[int]]:
        w, h = display.width, display.height
        frame: List[List[int]] = [[0]*w for _ in range(h)]
        x = int((t * 5) % w)
        for y in range(h):
            frame[y][x] = 1
        return frame

if __name__ == "__main__":
    Example().run()
```

Guidelines
- Do not hardcode canvas size; always use `display.width/height`.
- Output ints 0/1 only; the harness packs to RBM.
- Prefer time‑based motion (`t`) so animation speed remains stable across pacing changes.
