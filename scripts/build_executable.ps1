#!/usr/bin/env pwsh
# Build standalone executable using PyInstaller

$ErrorActionPreference = "Stop"

Set-Location "$PSScriptRoot\.."

Write-Host "Building executable with PyInstaller..."
uv run python scripts/build_executable.py
