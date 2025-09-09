#!/bin/bash

# Simple setup script for flip disc server
set -e

echo "Setting up flip disc server..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Create/recreate virtual environment
if [ -d ".venv" ]; then
    echo "Removing existing virtual environment..."
    rm -rf .venv
fi

echo "Creating virtual environment..."
uv venv

echo "Installing dependencies..."
uv pip install -e '.[dev]'

echo "Setup complete!"
echo "To activate: uv venv"