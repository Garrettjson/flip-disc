Awesome—got your zip and did a full pass. I put a thorough, senior-engineer style review (architecture, data-flow, concrete diffs, and a prioritized change list) into a canvas so it’s easy to iterate on.

Here’s the punchy summary:

* \#1 fix: make a tiny `Frame` dataclass and pass it end-to-end (seq, produced\_ts, target\_ts, data). This clarifies timing, drops, and logging.
* Co-locate pacing and credits in the **hardware ticker**. One loop renders at `fps`, pops ≤1 frame, and issues credits equal to buffer free slots. This removes drift.
* Panel packing: replace any Python loops with a vectorized column-packer that matches the protocol (LSB=top, bit7=0). It’s a 10-line numpy change with big correctness/perf payoff.
* Keep your current slices: `anims/`, `gfx/`, `hw/`, `services/`, `workers/` are good. Add a tiny `core/` folder for shared types/clock, and move `PROTOCOL.md` under `hw/`.
* Spawn method: call `multiprocessing.set_start_method("spawn", force=True)` in `main()` for macOS/Linux parity.
* API surface: keep it small and explicit (`/status`, `/anim/{name}`, `/fps`, `/workers/restart`, `/serial/reconnect`). Include buffer sizes, drops, and serial state in `/status`.
* Tests: add 3 golden cases for `formats.py` + a short pacing test with the mock serial port.

If you open the canvas, you’ll find:

* A cleaned-up folder structure recommendation
* A precise data-flow (current vs. proposed)
* Minimal, copy-paste-able code snippets/diffs for:

  * `flipdisc/core/types.py` (new)
  * `hw/formats.py` column pack (vectorized, protocol-correct)
  * `services/hardware.py` single ticker (pacing + credits together)
  * `workers/ipc.py` (carry `seq` and timestamps)
  * `app.py` (force `spawn`)
* A quick-wins checklist and a future-nice-to-haves section
