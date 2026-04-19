#!/usr/bin/env python3
"""Validate that package version metadata stays aligned."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PACKAGE_NAME = "notewise"
ROOT = Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_version(pattern: str, text: str, source: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        raise ValueError(f"Could not find version in {source}")
    return match.group(1)


def get_versions() -> dict[str, str]:
    pyproject_text = _read_text(ROOT / "pyproject.toml")
    init_text = _read_text(ROOT / "src" / PACKAGE_NAME / "__init__.py")
    lock_text = _read_text(ROOT / "uv.lock")

    lock_pattern = (
        r'\[\[package\]\]\s+name\s*=\s*"'
        + re.escape(PACKAGE_NAME)
        + r'"\s+version\s*=\s*"([^"]+)"'
    )

    return {
        "pyproject.toml": _extract_version(
            r'^version\s*=\s*"([^"]+)"$',
            pyproject_text,
            "pyproject.toml",
        ),
        "src/notewise/__init__.py": _extract_version(
            r'^__version__\s*=\s*"([^"]+)"$',
            init_text,
            "src/notewise/__init__.py",
        ),
        "uv.lock": _extract_version(lock_pattern, lock_text, "uv.lock"),
    }


def _normalize_release_tag(tag: str) -> str:
    return tag[1:] if tag.startswith("v") else tag


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate package version metadata alignment.",
    )
    parser.add_argument(
        "--release-tag",
        help="Optional release tag to validate against the package version.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    versions = get_versions()
    distinct_versions = set(versions.values())

    if len(distinct_versions) != 1:
        print("Version metadata drift detected:", file=sys.stderr)
        for path, version in versions.items():
            print(f"- {path}: {version}", file=sys.stderr)
        return 1

    version = next(iter(distinct_versions))

    if args.release_tag is not None:
        normalized_tag = _normalize_release_tag(args.release_tag)
        if normalized_tag != version:
            print(
                "Release tag does not match package version:",
                file=sys.stderr,
            )
            print(f"- release tag: {args.release_tag}", file=sys.stderr)
            print(f"- package version: {version}", file=sys.stderr)
            return 1

    print(f"Version metadata is aligned: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
