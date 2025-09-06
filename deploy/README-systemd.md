# Deploying on Raspberry Pi with systemd

These steps install the Flip‑Disc server (FastAPI/uv) and the orchestrator (Bun) as systemd services so they start on boot and restart on failure.

## Prerequisites

- Raspberry Pi OS (Debian-based) with systemd (default)
- Git + Bun + uv
  - `sudo apt-get update && sudo apt-get install -y git curl`
  - Install Bun: see https://bun.sh (or `curl -fsSL https://bun.sh/install | bash`)
  - Install uv: `curl -Ls https://astral.sh/uv/install.sh | sh`

## Clone and set up the repo

```bash
cd /home/pi
git clone https://github.com/<owner>/flip-disc.git
cd flip-disc

# Server Python env
cd server && uv venv && uv sync && cd ..

# Media pipeline Python env
cd media_pipeline && uv venv && uv sync && cd ..

# Orchestrator deps
make bun-setup
```

## Install environment files

```bash
sudo mkdir -p /etc/flipdisc
sudo cp deploy/env/server.env.sample /etc/flipdisc/server.env
sudo cp deploy/env/orchestrator.env.sample /etc/flipdisc/orchestrator.env

# Edit as needed
sudo nano /etc/flipdisc/server.env
sudo nano /etc/flipdisc/orchestrator.env
```

Key toggles:
- `FLIPDISC_SERIAL=1` to enable RS‑485 writes (set device/baud accordingly)
- `PORT` in each env to set listen ports

## Install systemd units

Option A — one‑shot installer:

```bash
sudo bash deploy/install_systemd.sh
```

Option B — manual install:

```bash
sudo cp deploy/systemd/flipdisc-server.service /etc/systemd/system/
sudo cp deploy/systemd/flipdisc-orchestrator.service /etc/systemd/system/
sudo cp deploy/systemd/flipdisc-worker@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable flipdisc-server.service flipdisc-orchestrator.service
sudo systemctl start flipdisc-server.service flipdisc-orchestrator.service
```

### Installer overrides

You can customize where the services run from and which user they run as:

```bash
# Run services from /opt/flip-disc instead of the repo path
sudo PREFIX=/opt/flip-disc bash deploy/install_systemd.sh

# Set service user/group
sudo SERVICE_USER=pi SERVICE_GROUP=pi bash deploy/install_systemd.sh

# Choose a specific Python interpreter for the uv virtualenv
sudo UV_PYTHON=/usr/bin/python3.11 bash deploy/install_systemd.sh
```

The installer will:
- Create the uv virtualenv and sync deps if missing
- Run `bun install` for the orchestrator
- Write units with the correct absolute paths
- Create the media_pipeline venv and sync deps if missing
- Install a templated media pipeline unit `flipdisc-worker@.service`

Optional installer flags:

- `WORKERS="<id1> <id2>"` — enable and start these Python media pipeline worker instances immediately.
- `AUTO_ENABLE_WORKERS=1` — enable and start all workers that have env files under `/etc/flipdisc/` (files named `worker-<id>.env`).

## Check status and logs

```bash
systemctl status flipdisc-server.service
systemctl status flipdisc-orchestrator.service

journalctl -u flipdisc-server -f
journalctl -u flipdisc-orchestrator -f

## Media pipeline workers (templated unit)

Python media pipeline workers run as independent instances of a single template unit. Each instance has its own env file and lifecycle.

1) Create an env file for your worker id (example: `my-media-filter`):

```bash
sudo bash -c 'echo "ORCH_URL=http://localhost:8090" > /etc/flipdisc/worker-my-media-filter.env'
sudo nano /etc/flipdisc/worker-my-media-filter.env
```

2) Start and enable the worker instance:

```bash
sudo systemctl enable --now flipdisc-worker@my-media-filter
```

3) Check status and logs:

```bash
systemctl status flipdisc-worker@my-media-filter
journalctl -u flipdisc-worker@my-media-filter -f
```

Repeat with different ids for additional workers.

You can also auto-enable during install:

```bash
sudo WORKERS="<id1> <id2>" bash deploy/install_systemd.sh
# or
sudo AUTO_ENABLE_WORKERS=1 bash deploy/install_systemd.sh
```
```

## Updating the app

```bash
cd /home/pi/flip-disc
git pull
cd server && uv sync && cd ../media_pipeline && uv sync && cd ..
sudo systemctl restart flipdisc-server flipdisc-orchestrator
```

## Notes

- The service units assume the repo lives at `/home/pi/flip-disc`. If not, edit `WorkingDirectory` and `ExecStart` accordingly.
- The server reads `config/display.yaml` within the repo; adjust that file for panel topology and FPS.
- The orchestrator UI is at `http://<pi>:8090/`.
