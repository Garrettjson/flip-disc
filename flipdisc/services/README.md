This package contains long‑running runtime services (async tasks) that make up
the Flip‑Disc application. Each service has a clear lifecycle (start/stop):

- `hardware.py`: Owns pacing/timing, serial I/O, and the frame buffer.
- `worker_manager.py`: Spawns/manages animation worker processes, issues credits,
  collects frames, and enqueues them into the hardware buffer.
- `api.py`: FastAPI server that exposes control/status endpoints.

Services are orchestrated by the app entrypoint in `flipdisc/app.py`.

