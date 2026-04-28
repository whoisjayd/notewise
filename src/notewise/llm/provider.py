"""LLM provider configuration using LiteLLM."""

import logging
import warnings
from collections.abc import AsyncIterable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, cast

import litellm
import structlog
from litellm import acompletion, aresponses, completion_cost

from notewise._constants import (
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    GPT5_MODEL_MARKER,
    GPT5_REQUIRED_TEMPERATURE,
    LLM_ERROR_PAYLOAD_MARKERS,
    LLM_NUM_RETRIES,
    LLM_PAYLOAD_ERROR_SUMMARY,
    PYDANTIC_RESPONSE_USAGE_WARNING_PATTERN,
    RESPONSES_API_ALL_MODEL_PROVIDER_PREFIXES,
    RESPONSES_API_MODEL_MARKERS,
    RESPONSES_API_PROVIDER_PREFIXES,
)
from notewise.config import settings as config
from notewise.errors import LLMGenerationError as _LLMGenerationError
from notewise.logging import make_log_safe_text, redact_sensitive_text


logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)
_USAGE_COLLECTOR: ContextVar["UsageTotals | None"] = ContextVar(
    "notewise_usage_collector",
    default=None,
)
_ERROR_SUMMARY_LIMIT = 500


def suppress_litellm_noise() -> None:
    """Keep LiteLLM retry/info chatter out of the user-facing terminal."""
    runtime = cast(Any, litellm)
    runtime.set_verbose = False
    runtime.suppress_debug_info = True
    verbose_logger = getattr(runtime, "verbose_logger", None)
    if verbose_logger is not None:
        verbose_logger.setLevel(logging.WARNING)
        verbose_logger.propagate = True
        for handler in list(verbose_logger.handlers):
            verbose_logger.removeHandler(handler)
    warnings.filterwarnings(
        "ignore",
        message=PYDANTIC_RESPONSE_USAGE_WARNING_PATTERN,
        category=UserWarning,
        module=r"pydantic\..*",
    )


def _configure_litellm_runtime() -> None:
    """Backward-compatible wrapper for LiteLLM runtime noise suppression."""
    suppress_litellm_noise()


def _summarize_error(error: Exception) -> str:
    """Collapse exception text into one redacted, log-friendly summary line."""
    summary = redact_sensitive_text(" ".join(str(error).split()))
    summary = make_log_safe_text(summary)
    summary_lower = summary.lower()
    if any(marker in summary_lower for marker in LLM_ERROR_PAYLOAD_MARKERS):
        return LLM_PAYLOAD_ERROR_SUMMARY
    if len(summary) > _ERROR_SUMMARY_LIMIT:
        return f"{summary[: _ERROR_SUMMARY_LIMIT - 1]}..."
    return summary


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


# LLMGenerationError is imported from notewise.errors
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

    @staticmethod
    def _event_value(event: Any, key: str) -> Any:
        """Read a value from either object-style or dict-style LiteLLM events."""
        if isinstance(event, dict):
            return event.get(key)
        return getattr(event, key, None)

    def _validate_config(self) -> None:
        """
        Verify that the necessary API key for the selected model is set.
        Logs a warning if missing.
        """
        # We rely on Config to check environment variables,
        # but we can double check here for the specific model
        missing_config = config.get_missing_config_names_for_model(self.model)
        if missing_config:
            expected = ", ".join(missing_config)
            logger.warning(
                f"Provider config for model '{self.model}' ({expected}) not found "
                "in environment. Generation may fail."
            )
        elif not config.get_api_key_names_for_model(
            self.model
        ) and not config.get_required_env_names_for_model(self.model):
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

            provider_temperature = self._normalize_temperature(temperature)
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": provider_temperature,
                # LiteLLM handles exponential backoff for RateLimitError
                "num_retries": LLM_NUM_RETRIES,
            }

            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens

            response: Any | None = None
            content = ""
            for attempt in range(LLM_NUM_RETRIES + 1):
                if self._uses_responses_api():
                    response = await self._generate_responses(
                        system_prompt,
                        user_prompt,
                        temperature=provider_temperature,
                        max_tokens=max_tokens,
                    )
                    content = self._normalize_responses_content(response)
                else:
                    # LiteLLM's acompletion handles async requests to providers.
                    response = await acompletion(**kwargs)
                    if response.choices and response.choices[0].message.content:
                        content = self._normalize_content(
                            response.choices[0].message.content
                        )
                    else:
                        content = ""

                if content:
                    break
                if attempt == LLM_NUM_RETRIES:
                    raise LLMGenerationError(
                        "Received empty response from LLM provider"
                    )

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

            return self._clean_content(content)

        except LLMGenerationError:
            raise
        except Exception as e:
            error_summary = _summarize_error(e)
            logger.error(
                "llm.generation_failed",
                model=self.model,
                error_type=type(e).__name__,
                error=error_summary,
                exc_info=False,
            )
            raise LLMGenerationError(
                f"Failed to generate with {self.model}: {error_summary}"
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

    def _uses_responses_api(self) -> bool:
        """Return True for LiteLLM models that require the Responses API."""
        model_lower = self.model.strip().lower()
        provider, separator, _ = model_lower.partition("/")
        if not separator or provider not in RESPONSES_API_PROVIDER_PREFIXES:
            return False
        if provider in RESPONSES_API_ALL_MODEL_PROVIDER_PREFIXES:
            return True
        return any(marker in model_lower for marker in RESPONSES_API_MODEL_MARKERS)

    def _normalize_temperature(self, temperature: float) -> float:
        """Return a provider-supported temperature for the configured model."""
        if GPT5_MODEL_MARKER in self.model.strip().lower():
            return GPT5_REQUIRED_TEMPERATURE
        return temperature

    def _uses_streamed_responses_api(self) -> bool:
        """Return True when LiteLLM's final Responses payload omits text."""
        model_lower = self.model.strip().lower()
        provider, separator, _ = model_lower.partition("/")
        return bool(separator and provider in RESPONSES_API_ALL_MODEL_PROVIDER_PREFIXES)

    async def _generate_responses(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float,
        max_tokens: int | None,
    ) -> Any:
        """Generate text with LiteLLM's Responses API."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "instructions": system_prompt,
            "input": [{"role": "user", "content": user_prompt}],
            "temperature": temperature,
            "num_retries": LLM_NUM_RETRIES,
        }
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        if self._uses_streamed_responses_api():
            kwargs["stream"] = True
            stream = await aresponses(**kwargs)
            return await self._collect_responses_stream(stream)
        return await aresponses(**kwargs)

    async def _collect_responses_stream(
        self,
        stream: AsyncIterable[Any],
    ) -> dict[str, Any]:
        """Collect text and usage from LiteLLM Responses API stream events."""
        delta_parts: list[str] = []
        done_parts: list[str] = []
        final_response: Any | None = None

        async for chunk in stream:
            delta = self._event_value(chunk, "delta")
            if isinstance(delta, str):
                delta_parts.append(delta)

            text = self._event_value(chunk, "text")
            if isinstance(text, str) and text.strip():
                done_parts.append(text)

            part = self._event_value(chunk, "part")
            part_text = self._event_value(part, "text")
            if isinstance(part_text, str) and part_text.strip():
                done_parts.append(part_text)

            item = self._event_value(chunk, "item")
            item_content = self._event_value(item, "content")
            if item_content is not None:
                done_parts.extend(self._normalize_content(item_content).splitlines())

            response = self._event_value(chunk, "response")
            if response is not None:
                final_response = response

        output_text = "".join(delta_parts).strip()
        if not output_text:
            output_text = "\n".join(done_parts).strip()

        return {
            "output_text": output_text,
            "output": self._event_value(final_response, "output"),
            "usage": self._event_value(final_response, "usage"),
        }

    def _extract_usage(self, response: Any) -> tuple[int, int, int]:
        """Extract usage tuple from LiteLLM response object or dict-like payload."""
        usage: Any | None = getattr(response, "usage", None)
        if usage is None and isinstance(response, dict):
            usage = response.get("usage")
        if usage is None:
            return (0, 0, 0)

        if isinstance(usage, dict):
            prompt_raw = usage.get("prompt_tokens", usage.get("input_tokens"))
            completion_raw = usage.get(
                "completion_tokens",
                usage.get("output_tokens"),
            )
            total_raw = usage.get("total_tokens")
        else:
            prompt_raw = getattr(usage, "prompt_tokens", None) or getattr(
                usage,
                "input_tokens",
                None,
            )
            completion_raw = getattr(usage, "completion_tokens", None) or getattr(
                usage,
                "output_tokens",
                None,
            )
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
        usage = self._extract_usage(response)
        usage_payload = {
            "prompt_tokens": usage[0],
            "completion_tokens": usage[1],
            "total_tokens": usage[2],
        }
        call_type = "aresponses" if self._uses_responses_api() else "acompletion"
        for model in self._cost_model_candidates():
            try:
                # Use a sanitized usage-only payload so provider-prefixed OAuth
                # model names do not trigger LiteLLM auth helpers during costing.
                cost = completion_cost(
                    completion_response={"usage": usage_payload},
                    model=model,
                    call_type=call_type,
                )
                cost_value = max(0.0, float(cost or 0.0))
            except Exception:
                continue
            if cost_value > 0:
                return cost_value
        return 0.0

    def _cost_model_candidates(self) -> tuple[str, ...]:
        """Return LiteLLM model names to try for cost lookup."""
        model = self.model.strip()
        model_lower = model.lower()
        provider, separator, _ = model_lower.partition("/")
        candidates: list[str] = []
        if separator and provider in RESPONSES_API_PROVIDER_PREFIXES:
            candidates.append(self._strip_model_provider_prefix(model))
        else:
            candidates.append(model)
            if separator:
                candidates.append(model.partition("/")[2])
                nested_provider = model.partition("/")[2]
                if "/" in nested_provider:
                    candidates.append(nested_provider.partition("/")[2])
        return tuple(dict.fromkeys(candidate for candidate in candidates if candidate))

    @staticmethod
    def _strip_model_provider_prefix(model: str) -> str:
        """Remove the outer LiteLLM provider prefix from a model string."""
        _, separator, remainder = model.partition("/")
        return remainder if separator and remainder else model

    def _clean_content(self, content: str) -> str:
        """
        Remove markdown code block fencing if the LLM wraps the entire output in it.

        Args:
            content: Raw LLM output.

        Returns:
            Cleaned content string.
        """
        content = self._normalize_markdown_fences(content)
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

    def _normalize_markdown_fences(self, content: str) -> str:
        """Normalize fence-only lines so Markdown previews close code blocks."""
        normalized_lines: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped in {"```", "~~~"} or stripped.startswith(("```", "~~~")):
                normalized_lines.append(stripped)
            else:
                normalized_lines.append(line.rstrip())
        return "\n".join(normalized_lines).strip()

    def _normalize_content(self, content: Any) -> str:
        """Normalize string or block-style provider payloads to plain text."""
        if isinstance(content, str):
            return content.strip()

        def _extract_text(value: Any) -> list[str]:
            if value is None:
                return []
            if isinstance(value, str):
                stripped = value.strip()
                return [stripped] if stripped else []
            if isinstance(value, dict):
                for key in ("text", "content", "value"):
                    nested = value.get(key)
                    if isinstance(nested, str):
                        stripped = nested.strip()
                        return [stripped] if stripped else []
                    if isinstance(nested, (dict, list)):
                        return _extract_text(nested)
                return []
            if isinstance(value, list):
                parts: list[str] = []
                for item in value:
                    parts.extend(_extract_text(item))
                return parts

            text_attr = getattr(value, "text", None)
            if isinstance(text_attr, str):
                stripped = text_attr.strip()
                return [stripped] if stripped else []

            value_attr = getattr(value, "value", None)
            if isinstance(value_attr, str):
                stripped = value_attr.strip()
                return [stripped] if stripped else []

            return []

        return "\n".join(_extract_text(content)).strip()

    def _normalize_responses_content(self, response: Any) -> str:
        """Normalize LiteLLM Responses API payloads to plain text."""
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        if isinstance(response, dict):
            dict_output_text = response.get("output_text")
            if isinstance(dict_output_text, str) and dict_output_text.strip():
                return dict_output_text.strip()
            return self._normalize_content(response.get("output"))
        return self._normalize_content(getattr(response, "output", None))


def get_provider(model: str = DEFAULT_MODEL) -> LLMProvider:
    """
    Factory function to get an LLM provider instance.

    Args:
        model: LiteLLM-compatible model string.

    Returns:
        Configured LLMProvider instance.
    """
    return LLMProvider(model=model)
