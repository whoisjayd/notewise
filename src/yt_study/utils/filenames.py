"""Safe filename and path string utilities."""

from __future__ import annotations

import re
from pathlib import Path


_RESERVED = re.compile(
    r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)",
    re.IGNORECASE,
)


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a cross-platform filename.

    Rules applied:
    - Strip characters forbidden on Windows and POSIX (<>:"/\\|?* and NUL).
    - Remove ASCII control characters (0x00-0x1F, 0x7F).
    - Rename Windows reserved device names (CON, NUL, COM1-COM9, LPT1-LPT9).
    - Strip trailing dots and spaces (leading dots are preserved).
    - Collapse internal whitespace to a single space.
    - Truncate to 100 characters.
    - Return "untitled" for empty or dot-only results.
    """
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "", name)
    name = re.sub(r"\s+", " ", name)
    name = name.strip().rstrip(".")
    name = name[:100].rstrip(" .")
    if not name:
        return "untitled"
    if _RESERVED.match(name):
        name = f"_{name}"[:100].rstrip(" .")
        if not name:
            return "untitled"
    return name


def safe_output_path(base_dir: Path, filename: str) -> Path:
    """Return a Path using a sanitized filename inside base_dir."""
    return base_dir / sanitize_filename(filename)
