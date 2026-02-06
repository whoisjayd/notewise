"""LLM provider configuration using LiteLLM."""

import os
import time
from typing import Any

import structlog
from litellm import acompletion

from ...config import config
from ..telemetry import telemetry


logger = structlog.get_logger(__name__)


class LLMGenerationError(Exception):
    """Exception raised when LLM generation fails."""

    pass


class LLMProvider:
    """
    LLM provider interface using LiteLLM.

    Handles API key verification and text generation with retries.
    """

    def __init__(self, model: str = "gemini/gemini-2.0-flash"):
        """
        Initialize LLM provider.

        Args:
            model: LiteLLM-compatible model string (e.g., 'gemini/gemini-2.0-flash').
        """
        self.model = model
        self._validate_config()

    def _validate_config(self) -> None:
        """
        Verify that the necessary API key for the selected model is set.
        Logs a warning if missing.
        """
        # We rely on Config to check environment variables,
        # but we can double check here for the specific model
        key_name = config.get_api_key_name_for_model(self.model)
        if key_name:
            if not os.getenv(key_name):
                logger.warning(
                    f"API Key for model '{self.model}' ({key_name}) not found "
                    "in environment. Generation may fail."
                )
        else:
            # If we can't map the model to a specific key (unknown provider),
            # we assume the user knows what they are doing or it doesn't need
            # one (e.g. ollama)
            logger.debug(f"No specific API key mapping found for model: {self.model}")

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        trace_id: str | None = None,
    ) -> str:
        """
        Generate text using the configured LLM.

        Args:
            system_prompt: System/instruction prompt.
            user_prompt: User query/content.
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum tokens to generate (None for model default).
            trace_id: Optional trace ID for linking events in observability.

        Returns:
            Generated text content.

        Raises:
            LLMGenerationError: If generation fails after retries.
        """
        try:
            start_time = time.perf_counter()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                # LiteLLM handles exponential backoff for RateLimitError
                "num_retries": 3,
            }

            if max_tokens:
                kwargs["max_tokens"] = max_tokens

            # LiteLLM's acompletion handles async requests to various providers
            response = await acompletion(**kwargs)
            latency_ms = int((time.perf_counter() - start_time) * 1000)

            # Track usage and LLM observability
            try:
                usage = getattr(response, "usage", None)
                content = response.choices[0].message.content or ""

                provider = (
                    self.model.split("/")[0] if "/" in self.model else "unknown"
                )
                event_props = {
                    "$ai_model": self.model,
                    "$ai_provider": provider,
                    "$ai_model_parameters": {
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                    "$ai_latency_ms": latency_ms,
                    "$ai_input": messages,
                    "$ai_output": [{"role": "assistant", "content": content}],
                }

                if trace_id:
                    event_props["$ai_trace_id"] = trace_id

                if usage:
                    event_props.update({
                        "$ai_input_tokens": getattr(usage, "prompt_tokens", 0),
                        "$ai_output_tokens": getattr(usage, "completion_tokens", 0),
                        "$ai_total_tokens": getattr(usage, "total_tokens", 0),
                    })

                telemetry.capture_event("$ai_generation", event_props)
            except Exception:
                pass

            # safely extract content
            if not response.choices or not response.choices[0].message.content:
                raise LLMGenerationError("Received empty response from LLM provider")

            content = response.choices[0].message.content.strip()
            return self._clean_content(content)

        except Exception as e:
            logger.error("LLM generation failed", model=self.model, error=str(e))
            raise LLMGenerationError(
                f"Failed to generate with {self.model}: {str(e)}"
            ) from e

    def _clean_content(self, content: str) -> str:
        """
        Remove markdown code block fencing if the LLM wraps the entire output in it.

        Args:
            content: Raw LLM output.

        Returns:
            Cleaned content string.
        """
        # Check for triple backticks
        if content.startswith("```"):
            lines = content.splitlines()
            # Need at least fence start, content, fence end
            if len(lines) >= 2 and lines[0].strip().startswith("```"):
                # If the first line is just a fence (with optional language), remove it
                # Check if the last line is also a fence
                if lines[-1].strip() == "```":
                    return "\n".join(lines[1:-1]).strip()
                # Sometimes LLMs stop abruptly or formatting is weird;
                # if it starts with fence, we strip the first line.
                # If it ends with fence, strip that too.
                return "\n".join(lines[1:]).strip().removesuffix("```").strip()

        return content


def get_provider(model: str = "gemini/gemini-2.0-flash") -> LLMProvider:
    """
    Factory function to get an LLM provider instance.

    Args:
        model: LiteLLM-compatible model string.

    Returns:
        Configured LLMProvider instance.
    """
    return LLMProvider(model=model)
