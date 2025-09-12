#!/usr/bin/env bash
set -euo pipefail

echo "Setting up flip disc server..."

# Ensure uv is available
if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.cargo/bin:$PATH"
fi

# Create virtual environment if missing
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment (.venv)..."
  uv venv
else
  echo "Using existing virtual environment (.venv)"
fi

echo "Installing/updating dependencies..."
uv pip install -e '.[dev]'

echo "Setup complete!"
echo "Run: uv run python -m src.main"
