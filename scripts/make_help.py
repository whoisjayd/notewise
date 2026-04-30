"""Render grouped Makefile help from target comments."""

from __future__ import annotations

import re
import sys
from pathlib import Path


GROUP_PREFIX = "##@ "
TARGET_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+):.*?##\s*(.+)$")
HIDDEN_TARGETS = frozenset(
    {
        "help",
        "clean-cache",
        "clean-build",
        "clean-test",
        "clean-empty-dirs",
    }
)
GROUP_ORDER = (
    "Setup",
    "Code Quality",
    "Git Hooks",
    "Testing",
    "Build & Publish",
    "Cleanup",
    "Info",
    "Workflow Bundles",
)


def _read_targets(makefile_path: Path) -> list[tuple[str, list[tuple[str, str]]]]:
    groups: list[tuple[str, list[tuple[str, str]]]] = []
    group_indexes: dict[str, int] = {}
    current_group = "Other"
    current_targets: list[tuple[str, str]] = []

    def flush_group() -> None:
        nonlocal current_targets
        if current_targets:
            if current_group in group_indexes:
                groups[group_indexes[current_group]][1].extend(current_targets)
            else:
                group_indexes[current_group] = len(groups)
                groups.append((current_group, current_targets))
            current_targets = []

    for line in makefile_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(GROUP_PREFIX):
            flush_group()
            current_group = line.removeprefix(GROUP_PREFIX).strip()
            continue

        match = TARGET_PATTERN.match(line)
        if match:
            target = match.group(1)
            if target in HIDDEN_TARGETS:
                continue
            current_targets.append((target, match.group(2).strip()))

    flush_group()
    return groups


def main() -> int:
    detected_os = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    makefile_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("Makefile")
    groups = _read_targets(makefile_path)
    grouped_targets = dict(groups)

    print()
    print(f"notewise developer tasks (OS: {detected_os})")
    print()

    ordered_groups = [
        (group, grouped_targets.pop(group))
        for group in GROUP_ORDER
        if group in grouped_targets
    ]
    ordered_groups.extend(grouped_targets.items())

    for group, targets in ordered_groups:
        print(f"{group}:")
        for target, description in targets:
            print(f"  {target:<16} {description}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
