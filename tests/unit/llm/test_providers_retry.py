"""Tests for provider transient-failure retry/backoff delegation to LiteLLM."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import litellm
import pytest

from notewise._constants import LLM_NUM_RETRIES
from notewise.errors import LLMGenerationError
from notewise.llm.provider import LLMProvider


pytestmark = pytest.mark.usefixtures("mock_config")


def _mock_completion_response(content: str) -> MagicMock:
    """Build a minimal chat-completion-shaped mock response."""
    response = MagicMock()
    response.choices[0].message.content = content
    response.usage.prompt_tokens = 1
    response.usage.completion_tokens = 1
    response.usage.total_tokens = 2
    return response


async def test_generate_requests_litellm_retries_for_every_call():
    """notewise delegates rate-limit/timeout backoff to LiteLLM via num_retries."""
    with (
        patch("notewise.llm.provider.acompletion") as mock_acompletion,
        patch("notewise.llm.provider.completion_cost", return_value=0.0),
    ):
        mock_acompletion.return_value = _mock_completion_response("Generated content")

        provider = LLMProvider("gpt-4o")
        await provider.generate("sys", "user")

    assert mock_acompletion.call_args.kwargs["num_retries"] == LLM_NUM_RETRIES


async def test_generate_surfaces_terminal_rate_limit_error():
    """A persistent rate-limit error must surface as an LLMGenerationError."""
    rate_limit_error = litellm.RateLimitError(
        message="rate limit exceeded", llm_provider="openai", model="gpt-4o"
    )
    with patch(
        "notewise.llm.provider.acompletion", side_effect=rate_limit_error
    ) as mock_acompletion:
        provider = LLMProvider("gpt-4o")
        with pytest.raises(LLMGenerationError, match="rate limit"):
            await provider.generate("sys", "user")

    # A single call to acompletion is made; LiteLLM's own num_retries kwarg
    # (asserted above) is what drives its internal retry/backoff loop, not a
    # notewise-side retry loop around acompletion itself.
    mock_acompletion.assert_called_once()


async def test_generate_surfaces_terminal_timeout_error():
    """A persistent provider timeout must surface as a redacted LLMGenerationError."""
    timeout_error = litellm.Timeout(
        message="Request timed out after 60s", model="gpt-4o", llm_provider="openai"
    )
    with patch("notewise.llm.provider.acompletion", side_effect=timeout_error):
        provider = LLMProvider("gpt-4o")
        with pytest.raises(LLMGenerationError, match="timed out"):
            await provider.generate("sys", "user")


async def test_generate_retries_empty_content_up_to_configured_limit():
    """The provider's own empty-content retry loop is bounded by LLM_NUM_RETRIES."""
    with (
        patch("notewise.llm.provider.acompletion") as mock_acompletion,
        patch("notewise.llm.provider.completion_cost", return_value=0.0),
    ):
        mock_acompletion.return_value = _mock_completion_response("")

        provider = LLMProvider("gpt-4o")
        with pytest.raises(LLMGenerationError, match="empty response"):
            await provider.generate("sys", "user")

    assert mock_acompletion.call_count == LLM_NUM_RETRIES + 1
