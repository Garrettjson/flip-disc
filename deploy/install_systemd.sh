#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "This script must run with root privileges. Re-run with: sudo bash $0" >&2
  exit 1
fi

# Optional overrides (export before running):
#   PREFIX=/opt/flip-disc
#   SERVICE_USER=pi
#   SERVICE_GROUP=pi
#   UV_PYTHON=/usr/bin/python3.11   # specific interpreter for uv venv (optional)
#   WORKERS="text-scroll bouncing-dot"  # enable these worker instances
#   AUTO_ENABLE_WORKERS=1               # enable all workers with env files under /etc/flipdisc

SERVICE_USER="${SERVICE_USER:-pi}"
SERVICE_GROUP="${SERVICE_GROUP:-$SERVICE_USER}"

# Resolve repo paths (default to repo location; allow PREFIX override)
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
DEFAULT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="${PREFIX:-$DEFAULT_ROOT}"
SERVER_DIR="$REPO_ROOT/server"
ORCH_DIR="$REPO_ROOT"
WORKERS_DIR="$REPO_ROOT/workers"

if [[ ! -d "$SERVER_DIR" ]]; then
  echo "Expected server dir not found at $SERVER_DIR" >&2
  echo "If you intended to run from a different PREFIX, clone/copy the repo there first or omit PREFIX." >&2
  exit 1
fi

# Ensure uv venv exists (create/sync if missing)
UV_BIN="$SERVER_DIR/.venv/bin/uv"
if [[ ! -x "$UV_BIN" ]]; then
  echo "Creating uv virtualenv at $SERVER_DIR/.venv ..." >&2
  if [[ -n "${UV_PYTHON:-}" ]]; then
    sudo -u "$SERVICE_USER" -H bash -lc "cd '$SERVER_DIR' && uv venv --python '$UV_PYTHON'"
  else
    sudo -u "$SERVICE_USER" -H bash -lc "cd '$SERVER_DIR' && uv venv"
  fi
  sudo -u "$SERVICE_USER" -H bash -lc "cd '$SERVER_DIR' && uv sync"
fi

# Verify uv bin
if [[ ! -x "$UV_BIN" ]]; then
  echo "uv binary still not found at $UV_BIN" >&2
  exit 1
fi

# Ensure bun deps are installed for orchestrator
if ! BUN_BIN="$(command -v bun)"; then
  echo "bun is not installed or not in PATH. Install bun first (https://bun.sh)." >&2
  exit 1
fi
echo "Installing orchestrator dev deps with bun ..." >&2
sudo -u "$SERVICE_USER" -H bash -lc "cd '$ORCH_DIR/orchestrator' && bun install"

# Env directory
ENV_DIR="/etc/flipdisc"
mkdir -p "$ENV_DIR"

if [[ ! -f "$ENV_DIR/server.env" ]]; then
  cp "$DEFAULT_ROOT/deploy/env/server.env.sample" "$ENV_DIR/server.env"
  echo "Created $ENV_DIR/server.env (edit to configure server)." >&2
fi

if [[ ! -f "$ENV_DIR/orchestrator.env" ]]; then
  cp "$DEFAULT_ROOT/deploy/env/orchestrator.env.sample" "$ENV_DIR/orchestrator.env"
  echo "Created $ENV_DIR/orchestrator.env (edit to configure orchestrator)." >&2
fi

# Ensure workers uv venv exists (create/sync if missing)
UV_BIN_WORKERS="$WORKERS_DIR/.venv/bin/uv"
if [[ ! -x "$UV_BIN_WORKERS" ]]; then
  echo "Creating workers uv virtualenv at $WORKERS_DIR/.venv ..." >&2
  if [[ -n "${UV_PYTHON:-}" ]]; then
    sudo -u "$SERVICE_USER" -H bash -lc "cd '$WORKERS_DIR' && uv venv --python '$UV_PYTHON'"
  else
    sudo -u "$SERVICE_USER" -H bash -lc "cd '$WORKERS_DIR' && uv venv"
  fi
  sudo -u "$SERVICE_USER" -H bash -lc "cd '$WORKERS_DIR' && uv sync"
fi

# Sample worker env for text-scroll
if [[ ! -f "$ENV_DIR/worker-text-scroll.env" ]]; then
  cp "$DEFAULT_ROOT/deploy/env/worker-text-scroll.env.sample" "$ENV_DIR/worker-text-scroll.env"
  echo "Created $ENV_DIR/worker-text-scroll.env (edit to configure text-scroll worker)." >&2
fi

# Sample worker env for bouncing-dot
if [[ ! -f "$ENV_DIR/worker-bouncing-dot.env" ]]; then
  cp "$DEFAULT_ROOT/deploy/env/worker-bouncing-dot.env.sample" "$ENV_DIR/worker-bouncing-dot.env"
  echo "Created $ENV_DIR/worker-bouncing-dot.env (edit to configure bouncing-dot worker)." >&2
fi

# Write server unit
cat > /etc/systemd/system/flipdisc-server.service <<UNIT
[Unit]
Description=Flip-Disc Server (FastAPI via uv)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$SERVER_DIR
EnvironmentFile=$ENV_DIR/server.env
ExecStart=$UV_BIN run uvicorn server.api:app --host 0.0.0.0 --port \${PORT}
Restart=on-failure
RestartSec=2
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
UNIT

# Write orchestrator unit
cat > /etc/systemd/system/flipdisc-orchestrator.service <<UNIT
[Unit]
Description=Flip-Disc Orchestrator (Bun)
After=network-online.target flipdisc-server.service
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$ORCH_DIR
EnvironmentFile=$ENV_DIR/orchestrator.env
ExecStart=$BUN_BIN orchestrator/index.ts
Restart=on-failure
RestartSec=2
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable flipdisc-server.service
systemctl enable flipdisc-orchestrator.service
systemctl restart flipdisc-server.service || systemctl start flipdisc-server.service
systemctl restart flipdisc-orchestrator.service || systemctl start flipdisc-orchestrator.service

# Write worker template unit (templated instance: flipdisc-worker@<id>.service)
cat > /etc/systemd/system/flipdisc-worker@.service <<UNIT
[Unit]
Description=Flip-Disc Worker %i (Python)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$REPO_ROOT
EnvironmentFile=$ENV_DIR/worker-%i.env
Environment=PYTHONPATH=$REPO_ROOT
ExecStart=$UV_BIN_WORKERS run python workers/runner.py %i
Restart=on-failure
RestartSec=2
StartLimitIntervalSec=60
StartLimitBurst=5
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload

# Optionally enable workers specified via WORKERS env var
if [[ -n "${WORKERS:-}" ]]; then
  for wid in ${WORKERS}; do
    if [[ ! -f "$ENV_DIR/worker-${wid}.env" ]]; then
      if [[ -f "$DEFAULT_ROOT/deploy/env/worker-${wid}.env.sample" ]]; then
        cp "$DEFAULT_ROOT/deploy/env/worker-${wid}.env.sample" "$ENV_DIR/worker-${wid}.env"
        echo "Created $ENV_DIR/worker-${wid}.env from sample. Edit to customize." >&2
      else
        echo "No sample env for worker '${wid}'. Creating minimal env." >&2
        echo -e "# Auto-generated\nORCH_URL=http://localhost:8090" > "$ENV_DIR/worker-${wid}.env"
      fi
    fi
    systemctl enable --now "flipdisc-worker@${wid}" || true
  done
fi

# Optionally enable all workers with env files present
if [[ "${AUTO_ENABLE_WORKERS:-0}" != "0" ]]; then
  for envf in "$ENV_DIR"/worker-*.env; do
    [[ -e "$envf" ]] || continue
    wid="${envf##*/}"
    wid="${wid#worker-}"
    wid="${wid%.env}"
    systemctl enable --now "flipdisc-worker@${wid}" || true
  done
fi

echo "Installed and (re)started services. Check status with:"
echo "  systemctl status flipdisc-server flipdisc-orchestrator"
echo "Tail logs with:"
echo "  journalctl -u flipdisc-server -f"
echo "  journalctl -u flipdisc-orchestrator -f"
echo "To run the text-scroll worker as a service:"
echo "  sudo systemctl enable --now flipdisc-worker@text-scroll"
echo "Logs:"
echo "  journalctl -u flipdisc-worker@text-scroll -f"
if [[ -n "${WORKERS:-}" ]]; then
  echo "Requested worker instances enabled: ${WORKERS}"
fi
if [[ "${AUTO_ENABLE_WORKERS:-0}" != "0" ]]; then
  echo "Enabled all workers with env files under ${ENV_DIR}"
fi
