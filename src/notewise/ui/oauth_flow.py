"""Reusable OAuth/device-flow login helpers for LiteLLM providers."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from notewise._constants import (
    LLM_NUM_RETRIES,
    OAUTH_LOGIN_FAILURE_MESSAGE,
    OAUTH_LOGIN_PROVIDER_LABELS,
    OAUTH_LOGIN_SAFE_MODELS,
    OAUTH_LOGIN_STORAGE_GUIDANCE,
    OAUTH_LOGIN_SUCCESS_MESSAGE,
    OAUTH_LOGIN_TEST_INSTRUCTIONS,
    OAUTH_LOGIN_TEST_MAX_OUTPUT_TOKENS,
    OAUTH_LOGIN_TEST_PROMPT,
    OAUTH_LOGIN_TRIGGER_MESSAGE,
    OAUTH_UNSUPPORTED_PROVIDER_ERROR,
    RESPONSES_API_MODEL_MARKERS,
    RESPONSES_API_PROVIDER_PREFIXES,
)
from notewise.config import configure_oauth_token_storage, get_oauth_token_storage_paths
from notewise.errors import OAuthError
from notewise.logging import redact_sensitive_text


if TYPE_CHECKING:
    from rich.console import Console


def _resolve_console(console: Console | None) -> Console:
    """Return the provided console or create a fresh one for this flow."""
    from rich.console import Console

    return console if console is not None else Console()


def _uses_responses_api(model: str) -> bool:
    """Return True for OAuth models that require LiteLLM's Responses API."""
    model_lower = model.strip().lower()
    provider, separator, _ = model_lower.partition("/")
    if not separator or provider not in RESPONSES_API_PROVIDER_PREFIXES:
        return False
    return any(marker in model_lower for marker in RESPONSES_API_MODEL_MARKERS)


def _storage_guidance() -> str:
    """Return rendered OAuth storage guidance with concrete token paths."""
    storage_paths = ", ".join(
        f"{provider}: {path}"
        for provider, path in get_oauth_token_storage_paths().items()
    )
    return OAUTH_LOGIN_STORAGE_GUIDANCE.format(storage_paths=storage_paths)


async def run_oauth_login_async(
    provider: str,
    *,
    console: Console | None = None,
) -> bool:
    """Trigger LiteLLM's OAuth/device-flow login with a tiny test request."""
    active_console = _resolve_console(console)
    configure_oauth_token_storage()
    provider_label = OAUTH_LOGIN_PROVIDER_LABELS.get(provider, provider)
    model = OAUTH_LOGIN_SAFE_MODELS.get(provider)
    if model is None:
        error = OAuthError(OAUTH_UNSUPPORTED_PROVIDER_ERROR.format(provider=provider))
        active_console.print(
            "[red]"
            + OAUTH_LOGIN_FAILURE_MESSAGE.format(
                provider_label=provider_label,
                error=redact_sensitive_text(str(error)),
            )
            + "[/red]"
        )
        active_console.print(f"[dim]{_storage_guidance()}[/dim]")
        return False

    active_console.print(f"[cyan]{OAUTH_LOGIN_TRIGGER_MESSAGE}[/cyan]")
    try:
        if _uses_responses_api(model):
            from litellm import aresponses

            await aresponses(
                model=model,
                instructions=OAUTH_LOGIN_TEST_INSTRUCTIONS,
                input=[{"role": "user", "content": OAUTH_LOGIN_TEST_PROMPT}],
                max_output_tokens=OAUTH_LOGIN_TEST_MAX_OUTPUT_TOKENS,
                num_retries=LLM_NUM_RETRIES,
            )
        else:
            from litellm import acompletion

            messages: list[dict[str, Any]] = [
                {"role": "system", "content": OAUTH_LOGIN_TEST_INSTRUCTIONS},
                {"role": "user", "content": OAUTH_LOGIN_TEST_PROMPT},
            ]
            await acompletion(
                model=model,
                messages=messages,
                max_tokens=OAUTH_LOGIN_TEST_MAX_OUTPUT_TOKENS,
                num_retries=LLM_NUM_RETRIES,
            )
    except Exception as error:
        active_console.print(
            "[red]"
            + OAUTH_LOGIN_FAILURE_MESSAGE.format(
                provider_label=provider_label,
                error=redact_sensitive_text(str(error)),
            )
            + "[/red]"
        )
        active_console.print(f"[dim]{_storage_guidance()}[/dim]")
        return False

    active_console.print(
        "[green]"
        + OAUTH_LOGIN_SUCCESS_MESSAGE.format(
            provider_label=provider_label,
            model=model,
        )
        + "[/green]"
    )
    active_console.print(f"[dim]{_storage_guidance()}[/dim]")
    return True


def run_oauth_login(provider: str, *, console: Console | None = None) -> bool:
    """Synchronous wrapper for CLI and setup wizard use."""
    return asyncio.run(run_oauth_login_async(provider, console=console))
