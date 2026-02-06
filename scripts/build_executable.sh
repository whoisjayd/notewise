#!/usr/bin/env bash
# Build standalone executable using PyInstaller
set -e

cd "$(dirname "$0")/.."

echo "Building executable with PyInstaller..."
uv run python scripts/build_executable.py
