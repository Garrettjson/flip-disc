# Flip Disc Orchestrator

TypeScript orchestrator for managing flip disc display animations and coordinating workers. Built with Bun's modern APIs including native WebSocket server and Workers.

## Quick Start

### Setup
```bash
bun install
```

### Development
```bash
bun run dev
```

### Production
```bash
bun run start
```

The orchestrator runs on `http://localhost:3000`
- Web UI: http://localhost:3000
- WebSocket: ws://localhost:3000/ws
- API: http://localhost:3000/api/status

## Architecture

### Core Services
- **ServerCommunicationService** - WebSocket + REST client for flip disc server
- **FrameSchedulerService** - Credit system and timing management
- **Worker System** - Bun Workers for animation generation

### Credit System Flow
1. Orchestrator connects to server WebSocket
2. Server sends initial credits (buffer capacity)
3. Worker generates frame → Scheduler checks credits
4. If credits > 0: Send frame to server
5. Server immediately returns updated credits
6. Repeat at target frame rate

### Modern Bun Features Used
- **Native WebSocket Server** (`Bun.serve`) - No external dependencies
- **Bun Workers API** - Efficient animation workers
- **Native TypeScript** - Zero transpilation overhead
- **Built-in `fetch()`** - No node-fetch needed
- **Static file serving** - Automatic ETags and compression

## Project Structure

```
src/
├── controllers/         # Request handling logic
├── services/           # Core business logic
│   ├── ServerCommunicationService.ts
│   └── FrameSchedulerService.ts  
├── sockets/            # WebSocket handlers
├── workers/            # Animation workers
│   └── bouncing-dot-worker.ts
├── routes/             # API routes
├── types/              # TypeScript definitions
└── index.ts            # Main application
```

## Available Animations

### Bouncing Dot
Simple dot that bounces around the display canvas.

**Usage:**
- Click "Start Bouncing Dot" in web UI
- Or via WebSocket: `{"type": "start_animation", "worker_path": "./src/workers/bouncing-dot-worker.ts"}`

## Configuration

The orchestrator automatically discovers server configuration by connecting to:
- **Server API**: `http://localhost:8000/api/display`
- **Server WebSocket**: `ws://localhost:8000/ws/frames`

Override defaults by modifying `defaultServerConfig` in `ServerCommunicationService.ts`.

## API Endpoints

### WebSocket Messages (`/ws`)

**From UI to Orchestrator:**
```javascript
{"type": "start_animation", "worker_path": "..."}
{"type": "stop_animation"}
{"type": "get_status"}
```

**From Orchestrator to UI:**
```javascript
{"type": "credits_updated", "data": {...}}
{"type": "frame_preview", "data": {...}}
{"type": "status", "data": {...}}
```

### REST API
```
GET /api/status  # Orchestrator status
```

## Development

### Adding New Workers
1. Create worker file in `src/workers/`
2. Implement `WorkerMessage` interface
3. Handle `configure`, `generate`, `stop` commands
4. Return packed bitmap data as `Uint8Array`

### Worker Template
```typescript
self.onmessage = (event: MessageEvent<WorkerMessage>) => {
  const message = event.data;
  
  switch (message.command) {
    case 'configure':
      // Setup worker with display dimensions
      break;
    case 'generate': 
      // Generate and return frame data
      break;
    case 'stop':
      // Cleanup
      break;
  }
};
```

### Testing
```bash
# Unit tests (Bun)
bun test

# Lint and format (Biome)
bun run lint
bun run format
```

Notes
- Worker pipeline packs rows per-row (stride = ceil(width/8)), MSB-first, matching the server’s expected bitmap format.
- To run a full pipeline smoke, start the server (see server/README.md Testing) and then `bun run dev` here to connect and stream frames.

## Performance

- **Target FPS**: 15 (configurable)
- **Buffer Management**: Credit-based flow control
- **Worker Efficiency**: Bun's fast Worker implementation
- **Network**: Binary WebSocket frames to server

## Troubleshooting

**Orchestrator won't start**
- Ensure server is running on port 8000
- Check server health: `curl http://localhost:8000/api/health`

**Worker errors**
- Check worker file paths are correct
- Ensure worker implements all required message handlers
- Check browser console for TypeScript errors

**No frames being sent**
- Verify credit system: Check "Credits" in web UI
- Ensure server WebSocket connection is active
- Check server buffer status: `curl http://localhost:8000/api/status`
