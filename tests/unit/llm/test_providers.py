"""Tests for LLM provider integration."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from notewise.errors import LLMGenerationError
from notewise.llm import provider as provider_mod
from notewise.llm.provider import (
    LLMProvider,
    UsageTotals,
    _configure_litellm_runtime,
    _summarize_error,
    get_provider,
)


class AsyncChunks:
    """Minimal async iterator for mocked LiteLLM streams."""

    def __init__(self, chunks):
        self._chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._chunks)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


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
            patch("notewise.llm.provider.acompletion") as mock_acompletion,
            patch("notewise.llm.provider.completion_cost", return_value=0.0),
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
            patch("notewise.llm.provider.acompletion") as mock_acompletion,
            patch("notewise.llm.provider.completion_cost", return_value=0.0),
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
    async def test_generate_normalizes_block_content_payloads(self):
        """Structured content blocks should be normalized into plain text."""
        with (
            patch("notewise.llm.provider.acompletion") as mock_acompletion,
            patch("notewise.llm.provider.completion_cost", return_value=0.0),
        ):
            mock_response = MagicMock()
            mock_response.choices[0].message.content = [
                {"type": "text", "text": "First paragraph"},
                {"type": "output_text", "text": "Second paragraph"},
            ]
            mock_acompletion.return_value = mock_response

            provider = LLMProvider("gpt-4o")
            result = await provider.generate("sys", "user")

            assert result == "First paragraph\nSecond paragraph"

    @pytest.mark.asyncio
    async def test_generate_collects_usage_from_litellm_response(self):
        """Provider should accumulate prompt/completion metrics from response usage."""
        with (
            patch("notewise.llm.provider.acompletion") as mock_acompletion,
            patch(
                "notewise.llm.provider.completion_cost",
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
            patch("notewise.llm.provider.acompletion") as mock_acompletion,
            patch("notewise.llm.provider.completion_cost", return_value=0.0),
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
            patch("notewise.llm.provider.acompletion") as mock_acompletion,
            patch(
                "notewise.llm.provider.completion_cost",
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
            patch("notewise.llm.provider.acompletion") as mock_acompletion,
            patch("notewise.llm.provider.completion_cost", return_value=0.0),
        ):
            mock_acompletion.side_effect = Exception("API Error")

            provider = LLMProvider("gpt-4o")

            with pytest.raises(LLMGenerationError, match="Failed to generate"):
                await provider.generate("sys", "user")

    @pytest.mark.asyncio
    async def test_generate_failure_sanitizes_logged_and_raised_error(self):
        """Provider failures should keep details without leaking raw credentials."""
        secret = "AIza" + "C" * 32
        with (
            patch("notewise.llm.provider.acompletion") as mock_acompletion,
            patch("notewise.llm.provider.completion_cost", return_value=0.0),
            patch("notewise.llm.provider.logger.error") as mock_log_error,
        ):
            mock_acompletion.side_effect = Exception(f"gemini_api_key={secret}")

            provider = LLMProvider("gpt-4o")

            with pytest.raises(LLMGenerationError) as exc:
                await provider.generate("sys", "user")

        assert secret not in str(exc.value)
        assert "[REDACTED]" in str(exc.value)
        assert mock_log_error.call_args.kwargs["error_type"] == "Exception"
        assert secret not in mock_log_error.call_args.kwargs["error"]
        assert "[REDACTED]" in mock_log_error.call_args.kwargs["error"]
        assert mock_log_error.call_args.kwargs["exc_info"] is False

    @pytest.mark.asyncio
    async def test_generate_failure_does_not_log_provider_payload_tracebacks(self):
        """Provider payload errors should stay summary-only in logs."""
        prompt_text = "SECRET_PROMPT_TEXT"
        with (
            patch("notewise.llm.provider.acompletion") as mock_acompletion,
            patch("notewise.llm.provider.completion_cost", return_value=0.0),
            patch("notewise.llm.provider.logger.error") as mock_log_error,
        ):
            mock_acompletion.side_effect = Exception(
                f"request payload contained {prompt_text}"
            )

            provider = LLMProvider("gpt-4o")

            with pytest.raises(LLMGenerationError):
                await provider.generate("sys", "user")

        assert mock_log_error.call_args.kwargs["exc_info"] is False
        assert prompt_text not in mock_log_error.call_args.kwargs["error"]
        assert "suppressed" in mock_log_error.call_args.kwargs["error"]

    @pytest.mark.asyncio
    async def test_generate_reraises_existing_llm_generation_error(self):
        """Domain errors should not be double-wrapped by the provider."""
        with (
            patch("notewise.llm.provider.acompletion") as mock_acompletion,
            patch("notewise.llm.provider.completion_cost", return_value=0.0),
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
            patch("notewise.llm.provider.acompletion") as mock_acompletion,
            patch("notewise.llm.provider.completion_cost", return_value=0.0),
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
            patch("notewise.llm.provider.acompletion") as mock_acompletion,
            patch("notewise.llm.provider.completion_cost", return_value=0.0),
        ):
            mock_response = MagicMock()
            mock_response.choices[0].message.content = "Generated content"
            mock_acompletion.return_value = mock_response

            provider = LLMProvider("gpt-4o")
            await provider.generate("sys", "user", max_tokens=1)

        assert mock_acompletion.call_args.kwargs["max_tokens"] == 1

    @pytest.mark.asyncio
    async def test_generate_normalizes_gpt5_temperature_for_chat_completions(self):
        """GPT-5 chat-completion models should use LiteLLM's supported temperature."""
        with (
            patch("notewise.llm.provider.acompletion") as mock_acompletion,
            patch("notewise.llm.provider.completion_cost", return_value=0.0),
        ):
            mock_response = MagicMock()
            mock_response.choices[0].message.content = "Generated content"
            mock_acompletion.return_value = mock_response

            provider = LLMProvider("github_copilot/gpt-5-mini")
            await provider.generate("sys", "user", temperature=0.7)

        assert mock_acompletion.call_args.kwargs["temperature"] == 1.0

    @pytest.mark.asyncio
    async def test_generate_uses_responses_api_for_oauth_codex_models(self):
        """Codex models on OAuth providers should use LiteLLM Responses API."""
        with (
            patch("notewise.llm.provider.acompletion") as mock_acompletion,
            patch("notewise.llm.provider.aresponses") as mock_aresponses,
        ):
            mock_aresponses.return_value = SimpleNamespace(
                output_text="Responses content",
                usage={"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
            )

            provider = LLMProvider("github_copilot/gpt-5-codex")
            with provider.collect_usage() as usage:
                result = await provider.generate(
                    "sys",
                    "user",
                    temperature=0.2,
                    max_tokens=128,
                )

        assert result == "Responses content"
        mock_acompletion.assert_not_called()
        mock_aresponses.assert_called_once_with(
            model="github_copilot/gpt-5-codex",
            instructions="sys",
            input=[{"role": "user", "content": "user"}],
            temperature=1.0,
            num_retries=3,
            max_output_tokens=128,
        )
        assert usage == UsageTotals(
            prompt_tokens=3,
            completion_tokens=5,
            total_tokens=8,
        )

    @pytest.mark.asyncio
    async def test_generate_uses_responses_api_for_all_chatgpt_models(self):
        """ChatGPT subscription models should avoid LiteLLM chat bridge parsing."""
        with (
            patch("notewise.llm.provider.acompletion") as mock_acompletion,
            patch("notewise.llm.provider.aresponses") as mock_aresponses,
        ):
            mock_aresponses.return_value = AsyncChunks(
                [
                    SimpleNamespace(delta="ChatGPT "),
                    SimpleNamespace(delta="text"),
                    SimpleNamespace(
                        response=SimpleNamespace(
                            usage={
                                "input_tokens": 2,
                                "output_tokens": 3,
                                "total_tokens": 5,
                            },
                        ),
                    ),
                ]
            )

            provider = LLMProvider("chatgpt/gpt-5.2")
            with provider.collect_usage() as usage:
                result = await provider.generate("sys", "user")

        assert result == "ChatGPT text"
        mock_acompletion.assert_not_called()
        mock_aresponses.assert_called_once_with(
            model="chatgpt/gpt-5.2",
            instructions="sys",
            input=[{"role": "user", "content": "user"}],
            temperature=1.0,
            num_retries=3,
            stream=True,
        )
        assert usage == UsageTotals(
            prompt_tokens=2,
            completion_tokens=3,
            total_tokens=5,
        )

    @pytest.mark.asyncio
    async def test_generate_collects_dict_shaped_responses_stream_events(self):
        """Responses streams may yield dict-shaped chunks from LiteLLM."""
        with patch("notewise.llm.provider.aresponses") as mock_aresponses:
            mock_aresponses.return_value = AsyncChunks(
                [
                    {"delta": "Dict "},
                    {"delta": "stream"},
                    {
                        "response": {
                            "usage": {
                                "input_tokens": 4,
                                "output_tokens": 6,
                                "total_tokens": 10,
                            },
                        },
                    },
                ]
            )

            provider = LLMProvider("chatgpt/gpt-5.2")
            with provider.collect_usage() as usage:
                result = await provider.generate("sys", "user")

        assert result == "Dict stream"
        assert usage == UsageTotals(
            prompt_tokens=4,
            completion_tokens=6,
            total_tokens=10,
        )

    def test_normalize_responses_content_handles_structured_output(self):
        """Responses payloads without output_text should still flatten text blocks."""
        provider = LLMProvider("chatgpt/gpt-5-codex")
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "First"},
                        {"type": "text", "text": "Second"},
                    ],
                }
            ]
        }

        assert provider._normalize_responses_content(response) == "First\nSecond"

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
            "notewise.llm.provider.completion_cost",
            side_effect=RuntimeError("missing price map"),
        ):
            assert provider._extract_cost(response) == 0.0

    def test_validate_config_logs_debug_for_unknown_provider(self):
        """Unmapped models should log a debug hint instead of requiring a known key."""
        with (
            patch.object(
                type(provider_mod.config._get_instance()),
                "get_api_key_name_for_model",
                return_value=None,
            ),
            patch("notewise.llm.provider.logger.debug") as mock_debug,
        ):
            LLMProvider("custom/local-model")

        mock_debug.assert_called_once()

    def test_summarize_error_truncates_long_messages(self):
        """Very long error messages should be clipped to the summary limit."""
        summary = _summarize_error(Exception("x" * 600))
        assert summary.endswith("...")
        assert len(summary) == 502

    def test_summarize_error_escapes_unencodable_terminal_characters(self):
        """Error summaries should stay printable on non-UTF terminals."""
        with (
            patch("notewise.logging.sys.stderr", SimpleNamespace(encoding="cp1252")),
            patch("notewise.logging.sys.stdout", SimpleNamespace(encoding="cp1252")),
        ):
            summary = _summarize_error(Exception("retry later → unavailable"))

        assert summary == "retry later \\u2192 unavailable"

    def test_clean_content_normalizes_over_indented_markdown_fences(self):
        """Indented fence markers should not swallow following prose in previews."""
        provider = LLMProvider("gpt-4o")
        content = """Example:

```python
    import dis
    ```
- Next bullet
"""

        assert (
            provider._clean_content(content)
            == """Example:

```python
    import dis
```
- Next bullet"""
        )

    def test_configure_litellm_runtime_handles_missing_verbose_logger(self):
        """LiteLLM runtime setup should tolerate missing verbose logger objects."""
        runtime = MagicMock()
        runtime.verbose_logger = None

        with patch("notewise.llm.provider.litellm", runtime):
            _configure_litellm_runtime()

        assert runtime.set_verbose is False
        assert runtime.suppress_debug_info is True

    def test_configure_litellm_runtime_sets_verbose_logger_level(self):
        """Verbose LiteLLM loggers should be forced to error-only mode."""
        runtime = MagicMock()
        runtime.verbose_logger = MagicMock()

        with patch("notewise.llm.provider.litellm", runtime):
            _configure_litellm_runtime()

        runtime.verbose_logger.setLevel.assert_called_once_with(logging.ERROR)
        assert runtime.verbose_logger.propagate is False

    def test_extract_usage_handles_invalid_values(self):
        """Non-numeric usage payloads should fail closed to zero values."""
        provider = LLMProvider("gpt-4o")
        prompt, completion, total = provider._extract_usage(
            {
                "usage": {
                    "prompt_tokens": "bad",
                    "completion_tokens": object(),
                    "total_tokens": None,
                }
            }
        )

        assert (prompt, completion, total) == (0, 0, 0)

    def test_clean_content_handles_opening_fence_without_closing_fence(self):
        """Single-sided code fences should still drop the opening fence line."""
        provider = LLMProvider("gpt-4o")

        assert provider._clean_content("```markdown\nBody\n") == "Body"

    def test_normalize_content_handles_none_and_nested_payloads(self):
        """Nested block payloads should flatten into plain text safely."""
        provider = LLMProvider("gpt-4o")

        assert provider._normalize_content(None) == ""
        assert (
            provider._normalize_content(
                [
                    {"content": {"text": "First"}},
                    MagicMock(text="Second"),
                    MagicMock(value="Third"),
                ]
            )
            == "First\nSecond\nThird"
        )

    def test_normalize_content_ignores_unsupported_payloads(self):
        """Unsupported block shapes should be ignored instead of stringified."""
        provider = LLMProvider("gpt-4o")

        assert provider._normalize_content([{"foo": "bar"}, object()]) == ""
