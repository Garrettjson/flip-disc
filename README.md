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
- Workers (`workers/`)
  - One process per content stream; draw in the virtual canvas and post frames.
  - Example: `workers/bouncing_dot/` includes a local Tk preview and RBM posting.

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


**Getting Started**

One‑time setup
- Install uv (fast Python package manager and runner):
  - macOS: `brew install uv`
  - Cross‑platform: `curl -Ls https://astral.sh/uv/install.sh | sh`
- Initialize the server environment and deps:
  - `make uv-setup`

Project workflow
- Start server (reads `config/display.yaml`):
  - `make run-python-server`
  - Viewer at `http://localhost:8080/`
- Start orchestrator (Bun):
  - Install Bun (macOS): `brew install bun` (or see https://bun.sh)
  - One-time deps: `make bun-setup` (installs bun type packages)
  - Run: `make run-orchestrator`
  - Optional: override animation FPS during a session:
    - `curl -XPOST localhost:8090/fps -H 'Content-Type: application/json' -d '{"fps":20}'`
    - Clear override (follow server config FPS): `curl -XDELETE localhost:8090/fps`
  - Set active worker: `curl -XPOST localhost:8090/active -H 'Content-Type: application/json' -d '{"id":"bouncing-dot"}'`
- Start example worker (uses orchestrator by default):
  - `make run-worker`
  - Direct post to server (optional): `TARGET_URL=http://localhost:8080/ingest/rbm make run-worker`
- Update deps when `server/pyproject.toml` changes:
  - `make uv-sync` (optional `make uv-lock` to commit `server/uv.lock`)


**Bouncing Dot Demo**
- Start the server: `make run-server` (keep it running; viewer at `http://localhost:8080/`)
- Start the orchestrator: `make run-orchestrator`
- Set the active source to the bouncing‑dot worker:
  - `curl -XPOST localhost:8090/active -H 'Content-Type: application/json' -d '{"id":"bouncing-dot"}'`
- Run the demo worker (local Tk preview + posts frames):
  - `make run-worker`
- Open the viewer page and you should see the dot animating.
- Optional: send the worker directly to the server (bypass orchestrator):
  - `TARGET_URL=http://localhost:8080/ingest/rbm make run-worker`


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


**Implementation Details**
- Mapping & rendering: Vectorized NumPy (no fallbacks). Orientation with `np.rot90/flip`, packing via `np.packbits`, viewer via `np.kron` upscaling.
- Serial writer: Uses `aioserial` for non‑blocking writes. Per‑panel delay and inter‑frame gap supported.
- Pacing: Ring buffer with “keep latest” behavior; FPS enforced even if frames arrive faster.
- JSON: `orjson` response class; event loop uses `uvloop` where supported.


**Repo Map**
- `server/`: Python server (FastAPI app in `server/api.py`, engine in `server/engine.py`).
- `orchestrator/`: Minimal Node service.
- `workers/`: Example worker and shared RBM helpers.
- `config/display.yaml`: Topology and serial settings.
- `protocol/rbm_spec.md`: Wire format spec.
- `MONOREPO.md`: Additional run notes and flags.


**Next Steps**
- Add systemd unit and env files for running on a Pi via uv.
- Add optional metrics exporter (Prometheus) and richer viewer controls.
- Expand tests with golden RBM vectors and mapping parity checks.
