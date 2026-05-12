#!/usr/bin/env python3
"""Validate that package version metadata stays aligned."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


PACKAGE_NAME = "notewise"
ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class VersionSource:
    path: str
    pattern: str
    label: str | None = None


VERSION_SOURCES = (
    VersionSource("pyproject.toml", r'^version\s*=\s*"([^"]+)"$'),
    VersionSource("src/notewise/__init__.py", r'^__version__\s*=\s*"([^"]+)"$'),
    VersionSource(
        "website/src/lib/version.ts",
        r'^export const NOTEWISE_VERSION\s*=\s*"([^"]+)";$',
    ),
    VersionSource("docs/index.mdx", r"These docs track NoteWise `([^`]+)`"),
    VersionSource("docs/llms.txt", r"Current documented version: `([^`]+)`"),
    VersionSource("docs/llms-full.txt", r"Current documented version: `([^`]+)`"),
    VersionSource(
        "docs/skill.md",
        r"NoteWise `([^`]+)`",
        "docs/skill.md NoteWise mention",
    ),
    VersionSource(
        "docs/skill.md",
        r"- Version: `([^`]+)`",
        "docs/skill.md version field",
    ),
    VersionSource(
        "tests/unit/cli/test_updater.py",
        r'current_version="([^"]+)"',
        "tests/unit/cli/test_updater.py current_version fixture",
    ),
    VersionSource(
        "tests/unit/cli/test_updater.py",
        r'latest_version="([^"]+)"',
        "tests/unit/cli/test_updater.py no-update latest_version fixture",
    ),
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_version(pattern: str, text: str, source: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        raise ValueError(f"Could not find version in {source}")
    return match.group(1)


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in result.stdout.splitlines()]


def _extract_lock_version() -> str:
    lock_text = _read_text(ROOT / "uv.lock")
    lock_pattern = (
        r'\[\[package\]\]\s+name\s*=\s*"'
        + re.escape(PACKAGE_NAME)
        + r'"\s+version\s*=\s*"([^"]+)"'
    )
    return _extract_version(lock_pattern, lock_text, "uv.lock")


def get_versions() -> dict[str, str]:
    versions = {"uv.lock": _extract_lock_version()}
    for source in VERSION_SOURCES:
        source_text = _read_text(ROOT / source.path)
        versions[source.label or source.path] = _extract_version(
            source.pattern,
            source_text,
            source.label or source.path,
        )
    return versions


def find_untracked_version_mentions(version: str) -> list[str]:
    """Find package-version mentions that are not covered by VERSION_SOURCES."""
    covered_paths = {source.path for source in VERSION_SOURCES} | {"uv.lock"}
    mention_patterns = (
        re.compile(r"\bNoteWise\s+`(?P<version>\d+\.\d+\.\d+)`"),
        re.compile(r"\bCurrent documented version:\s+`(?P<version>\d+\.\d+\.\d+)`"),
        re.compile(r"\bVersion:\s+`(?P<version>\d+\.\d+\.\d+)`"),
        re.compile(r"\bNOTEWISE_VERSION\b.*(?P<version>\d+\.\d+\.\d+)"),
        re.compile(r"\b__version__\b.*(?P<version>\d+\.\d+\.\d+)"),
    )
    misses: list[str] = []
    for path in _tracked_files():
        relative_path = path.relative_to(ROOT).as_posix()
        if relative_path in covered_paths:
            continue
        try:
            text = _read_text(path)
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for pattern in mention_patterns:
                match = pattern.search(line)
                if match:
                    matched_version = match.group("version")
                    reason = "drift" if matched_version != version else "uncovered"
                    misses.append(
                        f"{relative_path}:{line_number}: {reason}: {line.strip()}"
                    )
                    break
    return misses


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

    untracked_mentions = find_untracked_version_mentions(version)
    if untracked_mentions:
        print(
            "Version mentions are not covered by scripts/check_version_sync.py:",
            file=sys.stderr,
        )
        for mention in untracked_mentions:
            print(f"- {mention}", file=sys.stderr)
        return 1

    print(f"Version metadata is aligned: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
