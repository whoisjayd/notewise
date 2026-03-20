"""Pure helper functions used by the core pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yt_study.llm.provider import UsageTotals
from yt_study.utils import sanitize_filename


def suffix_output_target(base: Path, video_id: str) -> Path:
    """Append a stable video-id suffix to an output file or directory name."""
    suffix = f" ({sanitize_filename(video_id)})"
    if base.suffix:
        return base.with_name(f"{base.stem}{suffix}{base.suffix}")
    return base.with_name(f"{base.name}{suffix}")


def coerce_usage_int(value: Any) -> int:
    """Convert usage values to non-negative ints without trusting mock objects."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(value.strip()))
        except ValueError:
            return 0
    return 0


def coerce_usage_float(value: Any) -> float:
    """Convert usage values to non-negative floats safely."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    if isinstance(value, str):
        try:
            return max(0.0, float(value.strip()))
        except ValueError:
            return 0.0
    return 0.0


def coerce_usage_totals(raw_usage: Any) -> UsageTotals:
    """Normalize usage collector output into a concrete UsageTotals object."""
    if isinstance(raw_usage, UsageTotals):
        return raw_usage
    return UsageTotals(
        prompt_tokens=coerce_usage_int(getattr(raw_usage, "prompt_tokens", 0)),
        completion_tokens=coerce_usage_int(getattr(raw_usage, "completion_tokens", 0)),
        total_tokens=coerce_usage_int(getattr(raw_usage, "total_tokens", 0)),
        cost_usd=coerce_usage_float(getattr(raw_usage, "cost_usd", 0.0)),
    )


def estimate_tokens_used(transcript_text: str) -> int:
    """Fallback token estimate used when precise usage accounting is unavailable."""
    return max(1, len(transcript_text) // 4)
