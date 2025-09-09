# Flip Disc Project Context

## Project Overview
Building a flip disc display system with:
- Physical: 7x28 flip disc display (Alpha Zeta manufacturer, currently 1 panel but designed for flexibility)
- Server (Python): Manages serial communication and frame buffer on Raspberry Pi
- Orchestrator (JS/Bun): Controls animations and coordinates workers
- Workers: Generate animation frames (starting simple, later p5.js/processing.js)
- Client: Web UI for control and preview

## Hardware Specifics
- Display: Alpha Zeta flip disc, 7x28 pixels per panel
- Each panel has its own controller receiving RS-485 signal
- Serial protocol constraints:
  - Must update ENTIRE panel at once (no single pixel updates)
  - Message format: `HEADER(0x80) + cfg + address + data + EOT(0x8F)`
  - Example: `msg = HEADER + cfg + address + data + EOT`
- Refresh rate: ~15 FPS typical, 30 FPS maximum possible
- Connected via RS-485 to Raspberry Pi serial port

## Key Architecture Decisions

### Frame Timing Strategy (Critical Design Decision)
- **Hybrid push-pull model** with frame pacing to ensure smooth animation
- Server maintains 0.5s buffer (15 frames at 30fps) and displays frames at constant rate
- **Credit system**: Server tells orchestrator how many frames it needs
  - Prevents buffer overflow and wasted computation
  - Workers check if they should produce frames after each delivery
- Server pulls from buffer at constant rate, uses buffer if no new frame ready
- Frame scheduler in orchestrator tracks `nextFrameTime` and `credits`

### Communication
- **WebSocket** for frame data and bidirectional timing communication
- **HTTP/REST** for configuration, control, and stats
- Binary frame format: `[4B frame_id][1B flags][2B width][2B height][N bytes packed bitmap]`
  - Flags byte: bit 0 = invert, bits 1-7 reserved for future use
  - Bitmap data is packed (8 pixels per byte)

### Technology Stack & Libraries
- **Server**: 
  - Python with `asyncio` for non-blocking operations
  - `aioserial` for async serial communication
  - `numpy` for frame reshaping
  - `FastAPI` for REST API and WebSocket
  - `uv` package manager for environment
- **Orchestrator**: 
  - JavaScript with Bun runtime
  - Worker Threads (not child processes) for animations
  - Routes organized in separate files in `routes/` folder
- **UI**: Simple web interface served by orchestrator with:
  - Live preview of current animation
  - Animation selection and start/stop controls
  - Server state and config display
  - FPS adjustment (capped at server's 30fps max)
  - Parameter controls for current animation

### Worker Architecture
- **Worker Threads** chosen over child processes for:
  - Lower memory overhead with shared memory
  - Faster communication via SharedArrayBuffer
  - Orchestrator isolation from worker failures still maintained
- Each worker = one animation type (bouncing dot, text display, etc.)
- Workers produce frames on-demand (not free-running)
- Supervisor pattern for automatic restart on crash
- Future: Both JS and Python workers supported, same pipeline

### Optimizations to Implement
1. **Dirty frame optimization**: Only send updates to panels that changed
2. **Frame deduplication**: Skip identical consecutive frames
3. **Adaptive FPS**: Reduce rate for static content
4. Compare frames per panel to minimize serial communication

### Project Structure
```
flip-disc-project/
├── server/
│   ├── src/
│   │   ├── main.py           # Entry point, starts FastAPI
│   │   ├── frame_buffer.py   # Async buffer with credits
│   │   ├── serial_controller.py # RS-485 communication
│   │   └── api.py           # REST and WebSocket endpoints
│   ├── pyproject.toml
│   └── config.toml          # Persisted display config
├── orchestrator/
│   ├── src/
│   │   ├── index.js         # Main orchestrator entry
│   │   ├── frame-scheduler.js # Timing and credits logic
│   │   ├── routes/          # Separate files per route
│   │   ├── workers/
│   │   │   ├── base.js      # Worker base class
│   │   │   ├── bounce.js    # Bouncing dot animation
│   │   │   └── text.js      # Text display worker
│   │   └── worker-supervisor.js # Crash recovery
│   ├── public/
│   │   └── index.html       # Control UI
│   └── package.json
└── scripts/
    ├── setup.sh
    └── start.sh
```

## Implementation Priorities
1. **Phase 1**: Core frame flow (Server ↔ Orchestrator ↔ Simple Worker)
2. **Phase 2**: Basic UI for control and preview
3. **Phase 3**: Optimizations (dirty frames, deduplication)
4. **Phase 4**: Complex workers (p5.js animations)
5. **Future**: Python workers for image/video processing

## Configuration Management
- `.env` files for environment-specific settings (IPs, ports)
- `config.toml` for persisted display configuration
- Runtime API for temporary adjustments
- Display config communicated from server to orchestrator on connect

## Error Recovery Requirements
- Workers must not crash orchestrator (isolation via Worker Threads)
- Automatic worker restart on failure
- Server and orchestrator should auto-recover from crashes
- Maintain frame buffer through temporary network interruptions

## Testing Strategy
- Basic smoke tests for frame flow
- Unit tests for buffer management
- Integration tests for complete pipeline
- Mock serial controller for testing without hardware

## Design Constraints & Considerations

### Network Topology
- Orchestrator runs either on Raspberry Pi OR nearby computer on same network
- Low latency assumed (local network only)
- WebSocket connection must handle reconnection gracefully

### Frame Data Processing
- Server splits full display data into panel-specific data
- Reshaping uses numpy for efficiency
- Binary packing for minimal bandwidth usage

### Animation Requirements
- Start with simple geometric patterns
- Progress to p5.js/processing.js complex animations
- p5.js animations must use `noLoop()` and manual `redraw()` for frame control
- Future: Live video processing pipeline (Python worker)

### Why These Technology Choices
- **Python server**: Established serial communication libraries, numpy for efficient bit manipulation
- **Bun orchestrator**: Fast, built-in TypeScript, good worker thread support
- **Worker threads over processes**: Better for simple animations, shared memory benefits
- **WebSocket + REST split**: Real-time for frames, REST for control/config
- **Binary frame format**: Minimize bandwidth, efficient packing/unpacking

## Common Pitfalls to Avoid
- Don't let workers free-run (wastes CPU, fills buffer)
- Remember panel updates must be complete (no partial updates)
- Account for RS-485 communication speed limits
- Ensure frame timing ownership is clear (server owns display rate)
- Handle disconnections gracefully (both network and serial)

## Future Extensibility
- Multiple display support (multiple server instances)
- Python workers for computer vision/video processing
- Playlist/scheduling system for animations
- Remote control via web API
- Effect pipeline for post-processing (invert, flip, threshold)