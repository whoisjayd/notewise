# Build Scripts

This directory contains scripts for building and packaging yt-study.

## Available Scripts

### `build_executable.py`

Python script that builds standalone executables using PyInstaller with compression.

**Features:**

- Auto-detects platform (Windows/macOS/Linux)
- Creates platform-specific executables with proper extensions
- Compresses executables into archives:
  - Windows: `.zip` (ZIP deflate, compression level 9)
  - macOS/Linux: `.tar.gz` (gzip compression)
- Bundles all dependencies
- Cleans up build artifacts automatically

**Usage:**

```bash
uv run python scripts/build_executable.py
```

### `build_executable.sh` (Linux/macOS)

Bash wrapper for the build script.

**Usage:**

```bash
bash scripts/build_executable.sh
# or
make build-exe
```

### `build_executable.ps1` (Windows)

PowerShell wrapper for the build script.

**Usage:**

```powershell
.\scripts\build_executable.ps1
# or
make build-exe
```

## Output

All build artifacts are placed in `dist/release/`:

### Executables (uncompressed)

- Windows: `yt-study-windows.exe`
- macOS: `yt-study-macos`
- Linux: `yt-study-linux`

### Archives (compressed)

- Windows: `yt-study-windows.zip`
- macOS: `yt-study-macos.tar.gz`
- Linux: `yt-study-linux.tar.gz`

## CI/CD Integration

The release workflow automatically:

1. Builds executables for all platforms
2. Compresses them into archives
3. Uploads both executables and archives as GitHub release assets
