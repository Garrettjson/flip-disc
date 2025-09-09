# Flip Disc Server

Python server for managing flip disc display panels via RS-485 communication. Handles frame buffering, panel mapping, and provides REST/WebSocket APIs for orchestrator communication.

## Quick Start

### Setup
```bash
./setup.sh
uv venv
```

### Run Server
```bash
python -m src.main
```

Server runs on `http://0.0.0.0:8000`
- API docs: http://localhost:8000/docs  
- WebSocket: ws://localhost:8000/ws/frames

### Run Tests
```bash
pytest tests/ -v
```

## Configuration

Edit `config.toml` to configure your panel layout:

```toml
[canvas]
width = 28
height = 7

[serial]
port = "/dev/ttyUSB0"
baudrate = 9600
mock = true  # Set false for real hardware

[[panels]]
id = "main"
address = 0
# ... panel configuration
```

## Architecture

### Core Components
- **Configuration System** - Flexible panel arrangements with orientations
- **Frame Buffer** - Async buffer with credit system (prevents overflow)
- **Serial Controller** - Mock/hardware writers with RS-485 protocol  
- **Panel Mapper** - Canvas-to-panel conversion with transformations
- **FastAPI Application** - REST + WebSocket APIs

### Credit System
The server implements a credit-based flow control system:
- Server maintains 0.5s buffer (15 frames at 30fps)
- Orchestrator gets "credits" indicating how many frames can be sent
- Prevents buffer overflow and wasted computation
- Real-time credit updates via WebSocket

## API Endpoints

### REST (Configuration & Control)
```
GET  /api/display       # Canvas dimensions for orchestrator setup
GET  /api/status        # Buffer health and connection status
GET  /api/config        # Full configuration details
POST /api/control/start # Start display loop
POST /api/control/test/{pattern} # Send test patterns
GET  /api/health        # Health check
```

### WebSocket (Frame Data)
```
/ws/frames              # Binary frame delivery + credit updates
```

Frame format: `[4B frame_id][1B flags][2B width][2B height][data]`

## Panel Configurations

### Single Panel (28×7)
```toml
[canvas]
width = 28
height = 7

[[panels]]
id = "main"
address = 0
[panels.origin]
x = 0
y = 0
[panels.size]
width = 28
height = 7
```

### Stacked Panels (14×28)  
```toml
[canvas]
width = 28
height = 14

[[panels]]
id = "top"
address = 0
[panels.origin]
x = 0
y = 0

[[panels]]
id = "bottom"
address = 1
[panels.origin]
x = 0
y = 7
```

### Panel Orientations
- `normal` - No transformation
- `rot90`, `rot180`, `rot270` - Clockwise rotations
- `fliph`, `flipv` - Horizontal/vertical flip

## Development

### Mock vs Hardware
Set `mock = true` in config.toml for development without hardware.

Mock controller:
- Logs what would be sent to panels
- Simulates realistic timing delays
- Perfect for development and testing

### Test Patterns
```bash
curl -X POST http://localhost:8000/api/control/test/checkerboard
curl -X POST http://localhost:8000/api/control/test/border
curl -X POST http://localhost:8000/api/control/test/solid
```

### Testing
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_config.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Code Quality
```bash
# Lint code
ruff check src/

# Format code  
ruff format src/

# Type checking (if mypy installed)
mypy src/
```

## Hardware Integration

### RS-485 Protocol
- Header: `0x80`
- Config byte based on data length and refresh mode
- Panel address (0-255)
- Packed bitmap data (8 pixels per byte, MSB first)
- End of transmission: `0x8F`

Message: `0x80 + cfg + addr + data + 0x8F`

### Serial Settings
- Default: 9600 baud, 8N1
- Configurable via config.toml
- Async communication with aioserial

## Troubleshooting

### Common Issues

**Server won't start**
- Check config.toml syntax
- Verify panel configurations don't overlap
- Ensure virtual environment is activated

**Serial connection fails**
- Check serial port permissions: `sudo usermod -a -G dialout $USER`  
- Verify port exists: `ls /dev/tty*`
- Try different baud rates

**Tests failing**
- Ensure virtual environment activated
- Run `uv pip install -e '.[dev]'` to install test dependencies

### Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Set environment variable: `export LOG_LEVEL=DEBUG`

## Production Deployment

### Raspberry Pi Setup
1. Run setup script: `./setup.sh`
2. Configure real serial port in config.toml
3. Set `mock = false` in config
4. Add to systemd or supervisor for auto-start

### Performance
- Target: 30 FPS maximum (hardware limit)
- Typical: 15 FPS for smooth animation
- Buffer: 0.5s at target FPS (configurable)

### Security
- Configure CORS appropriately for production
- Use reverse proxy (nginx) if exposing publicly
- Consider authentication for control endpoints