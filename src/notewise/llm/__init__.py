"""LLM package — LiteLLM wrapper and prompts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from .provider import LLMProvider, UsageTotals, get_provider


__all__ = ["LLMProvider", "UsageTotals", "get_provider"]


def __getattr__(name: str) -> Any:
    """Load the provider API only when a caller requests it."""
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from . import provider

    return getattr(provider, name)
