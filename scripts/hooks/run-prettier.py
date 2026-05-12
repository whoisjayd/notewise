#!/usr/bin/env python3
"""Run the website-managed Prettier binary against staged repo paths."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WEBSITE = ROOT / "website"


def main() -> int:
    paths = [
        str(resolved)
        for path in sys.argv[1:]
        if not (resolved := (ROOT / path).resolve()).is_relative_to(ROOT / "docs")
    ]
    if not paths:
        return 0

    return subprocess.call(
        ["bun", "--cwd", str(WEBSITE), "prettier", "--write", *paths],
        cwd=ROOT,
    )


if __name__ == "__main__":
    raise SystemExit(main())
