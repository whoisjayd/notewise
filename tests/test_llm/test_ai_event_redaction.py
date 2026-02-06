"""Test AI event redaction in telemetry."""

from unittest.mock import MagicMock, patch

import pytest

from yt_study.core.llm.providers import LLMProvider


@pytest.mark.asyncio
async def test_ai_generation_event_redacts_content():
    """Test that AI input and output content is redacted in telemetry events."""

    with (
        patch("yt_study.core.llm.providers.acompletion") as mock_completion,
        patch("yt_study.core.llm.providers.telemetry") as mock_telemetry,
    ):
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is the AI generated response"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150

        mock_completion.return_value = mock_response

        # Create provider and generate
        provider = LLMProvider(model="gemini/gemini-2.0-flash")
        await provider.generate(
            system_prompt="You are a helpful assistant",
            user_prompt="What is the capital of France?",
            temperature=0.7,
        )

        # Verify telemetry was called
        assert mock_telemetry.capture_event.called
        event_name, event_props = mock_telemetry.capture_event.call_args[0]

        # Verify event name
        assert event_name == "$ai_generation"

        # Verify input is redacted
        assert "$ai_input" in event_props
        ai_input = event_props["$ai_input"]
        assert isinstance(ai_input, list)
        assert len(ai_input) == 2  # system and user messages

        # Check that content is redacted
        for msg in ai_input:
            assert msg["content"] == "<REDACTED>"
            assert "content_length" in msg
            assert msg["content_length"] > 0

        # Verify output is redacted
        assert "$ai_output" in event_props
        ai_output = event_props["$ai_output"]
        assert isinstance(ai_output, list)
        assert len(ai_output) == 1
        assert ai_output[0]["content"] == "<REDACTED>"
        assert ai_output[0]["content_length"] > 0

        # Verify metadata is still present
        assert event_props["$ai_model"] == "gemini/gemini-2.0-flash"
        assert event_props["$ai_provider"] == "gemini"
        assert event_props["$ai_input_tokens"] == 100
        assert event_props["$ai_output_tokens"] == 50
        assert event_props["$ai_total_tokens"] == 150
        assert "$ai_latency_ms" in event_props

        # Verify actual content is NOT in the event
        assert "You are a helpful assistant" not in str(event_props)
        assert "What is the capital of France?" not in str(event_props)
        assert "This is the AI generated response" not in str(event_props)


@pytest.mark.asyncio
async def test_ai_generation_event_includes_trace_id():
    """Test that trace ID is included when provided."""

    with (
        patch("yt_study.core.llm.providers.acompletion") as mock_completion,
        patch("yt_study.core.llm.providers.telemetry") as mock_telemetry,
    ):
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"
        mock_response.usage = None

        mock_completion.return_value = mock_response

        # Create provider and generate with trace_id
        provider = LLMProvider(model="gemini/gemini-2.0-flash")
        await provider.generate(
            system_prompt="System",
            user_prompt="User",
            trace_id="test-trace-123",
        )

        # Verify trace_id is in event
        event_name, event_props = mock_telemetry.capture_event.call_args[0]
        assert event_props["$ai_trace_id"] == "test-trace-123"
