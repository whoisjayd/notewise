# 📥 Installation

`yt-study` is a Python application compatible with **Python 3.10** and newer. Choose the method that best fits your workflow.

---

## 🐍 Standard Installation

The recommended way to install for most users is via `pip`:

```bash
pip install yt-study
```

---

## ⚡ Fast Installation (uv)

If you use **[uv](https://github.com/astral-sh/uv)**, you can run `yt-study` instantly without polluting your global environment:

### Run without installing
```bash
uvx yt-study --help
```

### Install as a permanent tool
```bash
uv tool install yt-study
```

---

## 🛠️ Development Installation

For contributors or those who want the latest features from the source:

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

---

## 📦 Binary Releases

For users who prefer not to use Python directly, we provide standalone executables for Windows, macOS, and Linux on our [Releases page](https://github.com/whoisjayd/yt-study/releases).

---

## ❓ Troubleshooting

### "Command not found"
Ensure your Python user bin directory is in your `PATH`.

- **Windows**: `%APPDATA%\Python\Python3x\Scripts`
- **Linux/macOS**: `~/.local/bin`

### Virtual Environments
It is highly recommended to install `yt-study` in a virtual environment to avoid conflicts:

```bash
# Create environment
python -m venv venv

# Activate (Linux/macOS)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install
pip install yt-study
```
