"""Tests for LLM provider integration."""

from unittest.mock import MagicMock, patch

import pytest

from yt_study.errors import LLMGenerationError
from yt_study.llm.provider import (
    LLMProvider,
    UsageTotals,
    get_provider,
)


class TestLLMProvider:
    """Test LLMProvider class."""

    def test_init_validation(self, mock_config):  # noqa: ARG002
        """Test initialization validates config."""
        # Should verify key existence (via logging or just passing)
        # Config fixture sets dummy keys, so this should pass
        provider = LLMProvider(model="gemini/gemini-pro")
        assert provider.model == "gemini/gemini-pro"

    @pytest.mark.asyncio
    async def test_generate_success(self):
        """Test successful generation."""
        with (
            patch("yt_study.llm.provider.acompletion") as mock_acompletion,
            patch("yt_study.llm.provider.completion_cost", return_value=0.0),
        ):
            # Setup mock response
            mock_response = MagicMock()
            mock_response.choices[0].message.content = "Generated content"
            mock_acompletion.return_value = mock_response

            provider = LLMProvider("gpt-4o")
            result = await provider.generate("sys", "user")

            assert result == "Generated content"
            mock_acompletion.assert_called_once()

            # Verify args passed to litellm
            args, kwargs = mock_acompletion.call_args
            assert kwargs["model"] == "gpt-4o"
            assert kwargs["messages"] == [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "user"},
            ]

    @pytest.mark.asyncio
    async def test_generate_cleanup_markdown(self):
        """Test cleaning of markdown code blocks from response."""
        with (
            patch("yt_study.llm.provider.acompletion") as mock_acompletion,
            patch("yt_study.llm.provider.completion_cost", return_value=0.0),
        ):
            mock_response = MagicMock()
            # LLM returns content wrapped in ```markdown ... ```
            mock_response.choices[
                0
            ].message.content = "```markdown\n# Title\nContent\n```"
            mock_acompletion.return_value = mock_response

            provider = LLMProvider("gpt-4o")
            result = await provider.generate("sys", "user")

            assert result == "# Title\nContent"

    @pytest.mark.asyncio
    async def test_generate_collects_usage_from_litellm_response(self):
        """Provider should accumulate prompt/completion metrics from response usage."""
        with (
            patch("yt_study.llm.provider.acompletion") as mock_acompletion,
            patch(
                "yt_study.llm.provider.completion_cost",
                return_value=0.0042,
            ),
        ):
            mock_response = MagicMock()
            mock_response.choices[0].message.content = "Generated content"
            mock_response.usage.prompt_tokens = 12
            mock_response.usage.completion_tokens = 34
            mock_response.usage.total_tokens = 46
            mock_acompletion.return_value = mock_response

            provider = LLMProvider("gpt-4o")
            with provider.collect_usage() as usage:
                await provider.generate("sys", "user")

            assert usage == UsageTotals(
                prompt_tokens=12,
                completion_tokens=34,
                total_tokens=46,
                cost_usd=0.0042,
            )

    @pytest.mark.asyncio
    async def test_generate_usage_defaults_to_zero_when_missing(self):
        """Missing usage metadata should not break generation metrics collection."""
        with (
            patch("yt_study.llm.provider.acompletion") as mock_acompletion,
            patch("yt_study.llm.provider.completion_cost", return_value=0.0),
        ):
            mock_response = MagicMock()
            mock_response.choices[0].message.content = "Generated content"
            mock_response.usage = None
            mock_acompletion.return_value = mock_response

            provider = LLMProvider("gpt-4o")
            with provider.collect_usage() as usage:
                await provider.generate("sys", "user")

            assert usage == UsageTotals()

    @pytest.mark.asyncio
    async def test_collect_usage_nested_scopes_roll_up_to_outer(self):
        """Nested usage scopes should preserve inner totals in the outer collector."""
        with (
            patch("yt_study.llm.provider.acompletion") as mock_acompletion,
            patch(
                "yt_study.llm.provider.completion_cost",
                return_value=0.0025,
            ),
        ):
            mock_response = MagicMock()
            mock_response.choices[0].message.content = "Generated content"
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 20
            mock_response.usage.total_tokens = 30
            mock_acompletion.return_value = mock_response

            provider = LLMProvider("gpt-4o")

            with (
                provider.collect_usage() as outer,
                provider.collect_usage() as inner,
            ):
                await provider.generate("sys", "user")

            assert inner == UsageTotals(
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
                cost_usd=0.0025,
            )
            assert outer == inner

    @pytest.mark.asyncio
    async def test_generate_failure(self):
        """Test generation failure raises custom exception."""
        with (
            patch("yt_study.llm.provider.acompletion") as mock_acompletion,
            patch("yt_study.llm.provider.completion_cost", return_value=0.0),
        ):
            mock_acompletion.side_effect = Exception("API Error")

            provider = LLMProvider("gpt-4o")

            with pytest.raises(LLMGenerationError, match="Failed to generate"):
                await provider.generate("sys", "user")

    @pytest.mark.asyncio
    async def test_generate_reraises_existing_llm_generation_error(self):
        """Domain errors should not be double-wrapped by the provider."""
        with (
            patch("yt_study.llm.provider.acompletion") as mock_acompletion,
            patch("yt_study.llm.provider.completion_cost", return_value=0.0),
        ):
            mock_acompletion.side_effect = LLMGenerationError("already normalized")

            provider = LLMProvider("gpt-4o")

            with pytest.raises(LLMGenerationError, match="already normalized") as exc:
                await provider.generate("sys", "user")

        assert str(exc.value) == "already normalized"

    @pytest.mark.asyncio
    async def test_generate_forwards_zero_max_tokens(self):
        """Explicit max_tokens=0 should still be forwarded to LiteLLM."""
        with (
            patch("yt_study.llm.provider.acompletion") as mock_acompletion,
            patch("yt_study.llm.provider.completion_cost", return_value=0.0),
        ):
            mock_response = MagicMock()
            mock_response.choices[0].message.content = "Generated content"
            mock_acompletion.return_value = mock_response

            provider = LLMProvider("gpt-4o")
            await provider.generate("sys", "user", max_tokens=0)

        assert mock_acompletion.call_args.kwargs["max_tokens"] == 0

    @pytest.mark.asyncio
    async def test_generate_forwards_positive_max_tokens(self):
        """Explicit positive max_tokens should be forwarded to LiteLLM."""
        with (
            patch("yt_study.llm.provider.acompletion") as mock_acompletion,
            patch("yt_study.llm.provider.completion_cost", return_value=0.0),
        ):
            mock_response = MagicMock()
            mock_response.choices[0].message.content = "Generated content"
            mock_acompletion.return_value = mock_response

            provider = LLMProvider("gpt-4o")
            await provider.generate("sys", "user", max_tokens=1)

        assert mock_acompletion.call_args.kwargs["max_tokens"] == 1

    def test_get_provider_factory(self):
        """Test factory function."""
        provider = get_provider("claude-3")
        assert isinstance(provider, LLMProvider)
        assert provider.model == "claude-3"

    def test_extract_usage_supports_dict_payloads(self):
        """Usage extraction should work for dict-like LiteLLM responses too."""
        provider = LLMProvider("gpt-4o")
        prompt, completion, total = provider._extract_usage(
            {
                "usage": {
                    "prompt_tokens": 4,
                    "completion_tokens": 8,
                }
            }
        )

        assert prompt == 4
        assert completion == 8
        assert total == 12

    def test_extract_cost_returns_zero_when_litellm_raises(self):
        """Cost extraction should fail closed when LiteLLM pricing lookup fails."""
        provider = LLMProvider("gpt-4o")
        response = MagicMock()
        with patch(
            "yt_study.llm.provider.completion_cost",
            side_effect=RuntimeError("missing price map"),
        ):
            assert provider._extract_cost(response) == 0.0
