# Flip Disc Display System

A complete system for controlling Alpha Zeta flip disc displays with smooth animations and flexible panel arrangements.

## Architecture

- **Server (Python)** - Manages hardware communication and frame buffering
- **Orchestrator (JS/Bun)** - Controls animations and coordinates workers  
- **Workers** - Generate animation frames (simple patterns → p5.js)
- **Client** - Web UI for control and preview

## Quick Start

### Server Setup
```bash
cd server
./setup.sh
uv venv
python -m src.main
```

Server runs on http://localhost:8000

### Run Tests
```bash
cd server
pytest tests/ -v
```

## Project Status

✅ **Server** - Complete with tests  
🚧 **Orchestrator** - In development  
⏳ **Workers** - Planned  
⏳ **Client** - Planned  

## Hardware Support

- **Display**: Alpha Zeta flip disc panels (7×28 pixels)
- **Communication**: RS-485 serial protocol
- **Layouts**: Single panel, stacked, side-by-side, custom arrangements
- **Refresh Rate**: Up to 30 FPS

## Development

Each component has its own setup and documentation:

- [`server/README.md`](server/README.md) - Python server documentation
- `orchestrator/README.md` - Coming soon
- `client/README.md` - Coming soon

## Configuration

The server uses `config.toml` for display configuration:

```toml
[canvas]
width = 28
height = 7

[serial]
mock = true  # Set false for real hardware

[[panels]]
id = "main"
address = 0
# Panel configuration...
```

## Features

- **Credit System** - Prevents buffer overflow with real-time flow control
- **Panel Mapping** - Automatic canvas-to-panel conversion with orientations
- **Mock Mode** - Full development workflow without hardware
- **Test Patterns** - Built-in patterns for hardware verification
- **WebSocket + REST** - Efficient frame delivery and control APIs

## Project Context

See [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) for detailed architecture decisions and implementation notes.