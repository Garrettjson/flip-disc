.PHONY: uv-setup uv-sync uv-lock bun-setup run-python-server run-worker run-orchestrator
.PHONY: uv-setup-workers uv-sync-workers uv-lock-workers

uv-setup:
	cd server && uv venv && uv sync

uv-sync:
	cd server && uv sync

uv-lock:
	cd server && uv lock

uv-setup-workers:
	cd workers && uv venv && uv sync

uv-sync-workers:
	cd workers && uv sync

uv-lock-workers:
	cd workers && uv lock

run-worker:
	cd workers && PYTHONPATH=.. uv run python bouncing_dot/main.py


run-orchestrator:
	bun orchestrator/index.ts

bun-setup:
	cd orchestrator && bun install

run-server:
	cd server && PYTHONPATH=.. uv run uvicorn server.api:app --host 127.0.0.1 --port 8080

.PHONY: install-systemd
install-systemd:
	sudo bash deploy/install_systemd.sh

.PHONY: run-python-server
run-python-server: run-server
