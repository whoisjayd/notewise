"""Tests for LLM provider integration."""

from unittest.mock import MagicMock, patch

import pytest

from yt_study.llm.providers import LLMGenerationError, LLMProvider, get_provider


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
        with patch("yt_study.llm.providers.acompletion") as mock_acompletion:
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
        with patch("yt_study.llm.providers.acompletion") as mock_acompletion:
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
    async def test_generate_failure(self):
        """Test generation failure raises custom exception."""
        with patch("yt_study.llm.providers.acompletion") as mock_acompletion:
            mock_acompletion.side_effect = Exception("API Error")

            provider = LLMProvider("gpt-4o")

            with pytest.raises(LLMGenerationError, match="Failed to generate"):
                await provider.generate("sys", "user")

    def test_get_provider_factory(self):
        """Test factory function."""
        provider = get_provider("claude-3")
        assert isinstance(provider, LLMProvider)
        assert provider.model == "claude-3"
