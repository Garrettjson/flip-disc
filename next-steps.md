# Next Steps and Ideas

This document tracks potential improvements and design options to evolve the system. Nothing here is committed — this is a menu of pragmatic upgrades we can pick from.

## Protocol Evolution

- RBM flags: Reserve bits in the RBM header `flags` for future formats.
  - `format_id` (bits 0–2): 0 = full bitmap (today), 1 = XOR-RLE, 2 = dirty-rects, others reserved.
  - `keyframe` (bit 3): frame is independent of history; deltas otherwise.
  - `compressed` (bit 4): zstd wrapper (optional, later).
- XOR-RLE (format 1): Send XOR mask vs. the last accepted frame, run-length encoded by bytes. Payload starts with `ref_seq` (uint32) followed by a simple byte-level RLE (zero-run and literal-run). Decoder reconstructs a full frame via `prev XOR mask`. Benefits: tiny payloads when only small areas change.
- Dirty Rects (format 2): Send a list of rects `{x,y,w,h}` each with packed bits (RBM for that rect). Decoder patches the previous frame in-place and enqueues the full frame. Benefits: only transmit changed regions.

Context note (panel-sized rects): Due to hardware constraints, we must send an entire sub-display’s bytes when any pixel in it changes. That means dirty-rects should be aligned to panel tiles (e.g., two rects of 28×7). This sacrifices fine-grained rect granularity by design, but still allows skipping RS-485 writes to panels that haven’t changed.

## Server Optimizations

- Per-panel dirty detection: Compare new `panelBits[id]` against the last written bytes; skip RS-485 write for unchanged panels. This aligns with hardware behavior (must send a full panel, but can omit panels that are unchanged).
- Optional PNG cache: Cache the last rendered PNG per `(seq, scale)` to avoid duplicate encodes when the viewer polls faster than the frame tick.
- Live tuning: Expose `/admin` endpoints to adjust `fps`, `buffer_ms`, `frame_gap_ms`, and `serial_interpanel_us` at runtime.
- Metrics: Add Prometheus `/metrics` with counters and gauges (buffer size, dropped frames, write durations, effective FPS).

## Orchestrator Improvements

- Credit-based WebSocket: Server grants ‘credits’ equal to buffer availability; orchestrator only sends when it has credits. Eliminates overfill and 429s entirely.
- Tick/Pull model: Server emits ticks at effective cadence; orchestrator responds with the latest frame. Server controls pace end-to-end.
- FPS override UI: Simple page to set/clear manual FPS for the active source.

## Worker Enhancements

- Diff encoders (optional):
  - XOR: emit XOR-RLE frames vs. previous.
  - Dirty-rects: emit panel-aligned rects to cut RS-485 writes by skipping unchanged panels.
- FPS awareness: Read `/fps` from orchestrator and render at (or slightly above) that rate.

- TTF font path (for larger canvases):
  - Add a TTF-based renderer using Pillow `ImageFont.truetype` to generate crisp glyphs at higher pixel heights (e.g., 12–24px).
  - Auto-trim glyphs horizontally, normalize baseline vertically, and expose font, size, and spacing in worker config.
  - Keep 1-bit thresholding to preserve flip-disc aesthetics; consider per-font thresholds.
  - Runtime trade-off: slight CPU cost and the need to ship a .ttf; enables multiple fonts/styles.

## Deployment & Ops

- Systemd unit on Pi with `uv run uvicorn server.api:app ...` and environment file for serial settings.
- Structured logging with request IDs; log sampled frame stats.
- Health checks: Extend `/healthz` to include simple self-test (e.g., mapping checksum, serial open state).

## Testing

- Golden vectors: Full RBM (black/white/checker), XOR of a single pixel change, and panel-aligned dirty rect updates. Round-trip tests for decode → full frame bytes.
- Timing tests: Verify effective FPS stability and buffer behavior under bursty ingest.

## Viewer/UI

- Panel-layer overlays: Color panel boundaries, show ‘dirty’ highlights when a panel is rewritten.
- Frame scrubber: Pause/resume and show last N frames in memory for debugging.

---

## Notes on Hardware Constraints (Dirty-Rects in Practice)

- Panels: 2 sub-displays (each 7×28). Hardware requires sending the full panel payload when any pixel within that panel changes.
- RS-485 writes: Each panel has its own address; to update both panels, send two back-to-back messages (one per panel). If only one panel changes, skip the other to cut bus traffic in half.
- Mapping: The server already maps the virtual canvas to panel-local bitmaps and assigns addresses; adding per-panel dirty detection is a local optimization within the server’s writer path.
