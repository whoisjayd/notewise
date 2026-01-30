# Installation Guide

`yt-study` is a Python application compatible with **Python 3.10** and newer.

## Standard Installation

The recommended way to install is via `pip`:

```bash
pip install yt-study
```

## Fast Installation (uv)

If you use [uv](https://github.com/astral-sh/uv), you can run `yt-study` instantly without polluting your global environment:

```bash
# Run once without installing
uvx yt-study --help

# Install as a permanent tool
uv tool install yt-study
```

## Development Installation

For contributors or those who want the latest bleeding-edge features:

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/whoisjayd/yt-study.git
    cd yt-study
    ```

2.  **Install dependencies**:
    We recommend using `uv` for fast syncing:
    ```bash
    uv sync
    ```
    Or standard pip:
    ```bash
    pip install -e .
    ```

## Troubleshooting

### "Command not found"
Ensure your Python user bin directory is in your `PATH`.
-   **Windows**: `%APPDATA%\Python\Python3x\Scripts`
-   **Linux/macOS**: `~/.local/bin`

### Virtual Environments
It is highly recommended to install `yt-study` in a virtual environment to avoid conflicts:

```bash
python -m venv venv
# Activate
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
# Install
pip install yt-study
```
