.PHONY: uv-setup uv-sync uv-lock bun-setup run-python-server run-worker run-orchestrator

uv-setup:
	cd server && uv venv && uv sync

uv-sync:
	cd server && uv sync

uv-lock:
	cd server && uv lock

run-worker:
	cd server && PYTHONPATH=.. uv run python ../workers/bouncing_dot/main.py

run-orchestrator:
	bun orchestrator/index.ts

bun-setup:
	cd orchestrator && bun install

run-server:
	cd server && uv run uvicorn server.api:app --host 127.0.0.1 --port 8080 -- --config ../config/display.yaml
