"""LLM provider configuration using LiteLLM."""

import os
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import structlog
from litellm import acompletion, completion_cost

from yt_study._constants import DEFAULT_MODEL, DEFAULT_TEMPERATURE, LLM_NUM_RETRIES
from yt_study.config import settings as config
from yt_study.errors import LLMGenerationError as _LLMGenerationError


logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)
_USAGE_COLLECTOR: ContextVar["UsageTotals | None"] = ContextVar(
    "yt_study_usage_collector",
    default=None,
)


@dataclass
class UsageTotals:
    """Token usage totals accumulated over one logical generation scope."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    def add(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cost_usd: float = 0.0,
    ) -> None:
        """Accumulate usage counts."""
        self.prompt_tokens += max(0, prompt_tokens)
        self.completion_tokens += max(0, completion_tokens)
        self.total_tokens += max(0, total_tokens)
        self.cost_usd += max(0.0, float(cost_usd))


# LLMGenerationError is imported from yt_study.errors
LLMGenerationError = _LLMGenerationError


class LLMProvider:
    """
    LLM provider interface using LiteLLM.

    Handles API key verification and text generation with retries.
    """

    def __init__(self, model: str = DEFAULT_MODEL):
        """
        Initialize LLM provider.

        Args:
            model: LiteLLM-compatible model string (e.g., 'gemini/gemini-2.5-flash').
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
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int | None = None,
    ) -> str:
        """
        Generate text using the configured LLM.

        Args:
            system_prompt: System/instruction prompt.
            user_prompt: User query/content.
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum tokens to generate (None for model default).

        Returns:
            Generated text content.

        Raises:
            LLMGenerationError: If generation fails after retries.
        """
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                # LiteLLM handles exponential backoff for RateLimitError
                "num_retries": LLM_NUM_RETRIES,
            }

            if max_tokens:
                kwargs["max_tokens"] = max_tokens

            # LiteLLM's acompletion handles async requests to various providers
            response = await acompletion(**kwargs)
            prompt_tokens, completion_tokens, total_tokens = self._extract_usage(
                response
            )
            call_cost_usd = self._extract_cost(response)
            collector = _USAGE_COLLECTOR.get()
            if collector is not None:
                collector.add(
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    call_cost_usd,
                )

            # safely extract content
            if not response.choices or not response.choices[0].message.content:
                raise LLMGenerationError("Received empty response from LLM provider")

            content = response.choices[0].message.content.strip()
            return self._clean_content(content)

        except Exception as e:
            logger.error(f"LLM generation failed with {self.model}: {e}", exc_info=True)
            raise LLMGenerationError(
                f"Failed to generate with {self.model}: {str(e)}"
            ) from e

    @contextmanager
    def collect_usage(self) -> Generator[UsageTotals, None, None]:
        """Collect prompt/completion token usage during enclosed generation calls."""
        totals = UsageTotals()
        parent_collector = _USAGE_COLLECTOR.get()
        token = _USAGE_COLLECTOR.set(totals)
        try:
            yield totals
        finally:
            _USAGE_COLLECTOR.reset(token)
            if parent_collector is not None:
                parent_collector.add(
                    totals.prompt_tokens,
                    totals.completion_tokens,
                    totals.total_tokens,
                    totals.cost_usd,
                )

    def _extract_usage(self, response: Any) -> tuple[int, int, int]:
        """Extract usage tuple from LiteLLM response object or dict-like payload."""
        usage: Any | None = getattr(response, "usage", None)
        if usage is None and isinstance(response, dict):
            usage = response.get("usage")
        if usage is None:
            return (0, 0, 0)

        if isinstance(usage, dict):
            prompt_raw = usage.get("prompt_tokens")
            completion_raw = usage.get("completion_tokens")
            total_raw = usage.get("total_tokens")
        else:
            prompt_raw = getattr(usage, "prompt_tokens", None)
            completion_raw = getattr(usage, "completion_tokens", None)
            total_raw = getattr(usage, "total_tokens", None)

        def _to_non_negative_int(value: Any) -> int:
            try:
                return max(0, int(value or 0))
            except (TypeError, ValueError):
                return 0

        prompt_tokens = _to_non_negative_int(prompt_raw)
        completion_tokens = _to_non_negative_int(completion_raw)
        total_tokens = _to_non_negative_int(
            total_raw or (prompt_tokens + completion_tokens)
        )
        return (prompt_tokens, completion_tokens, total_tokens)

    def _extract_cost(self, response: Any) -> float:
        """Extract estimated USD cost for a completion response via LiteLLM."""
        try:
            # Uses LiteLLM's model price map for provider-accurate cost estimation.
            cost = completion_cost(completion_response=response)
            return max(0.0, float(cost or 0.0))
        except Exception:
            return 0.0

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


def get_provider(model: str = DEFAULT_MODEL) -> LLMProvider:
    """
    Factory function to get an LLM provider instance.

    Args:
        model: LiteLLM-compatible model string.

    Returns:
        Configured LLMProvider instance.
    """
    return LLMProvider(model=model)
