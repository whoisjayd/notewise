"""Discovery and validation for custom OpenAI-compatible endpoints."""

from __future__ import annotations

import ipaddress
import json
import math
import re
from dataclasses import dataclass, field
from functools import cache
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import structlog

from notewise._constants import (
    CUSTOM_ENDPOINT_DISCOVERY_ACCEPT_HEADER,
    CUSTOM_ENDPOINT_HTTP_TIMEOUT_SECONDS,
    CUSTOM_ENDPOINT_VERIFICATION_INSTRUCTIONS,
    CUSTOM_ENDPOINT_VERIFICATION_MAX_OUTPUT_TOKENS,
    CUSTOM_ENDPOINT_VERIFICATION_PROMPT,
    CUSTOM_LLM_NAME_PATTERN,
    LLM_IDENTIFYING_HEADERS,
)
from notewise.errors import CustomEndpointError
from notewise.logging import make_log_safe_text, redact_sensitive_text


logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def _summarize_error(error: Exception) -> str:
    """Collapse exception text into one redacted, log-friendly summary line."""
    return make_log_safe_text(redact_sensitive_text(" ".join(str(error).split())))


if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True)
class CustomEndpointProfile:
    """A named OpenAI-compatible endpoint and its credential.

    `model_pricing` maps a discovered model id to (prompt_cost_per_token,
    completion_cost_per_token) in USD, captured from the endpoint's own
    `/v1/models` response when it exposes a `pricing` field (OpenRouter and
    other gateways use this convention; it is not OpenRouter-specific).
    Empty when the endpoint doesn't advertise pricing or hasn't been
    (re)discovered since this field was added.
    """

    name: str
    base_url: str
    api_key: str
    # Excluded from eq/hash: auxiliary metadata, not part of an endpoint's
    # identity, and a plain dict would make this (frozen, hashable) class
    # unhashable -- breaking any existing code that puts profiles in a set.
    model_pricing: dict[str, tuple[float, float]] = field(
        default_factory=dict, compare=False
    )


def parse_custom_endpoint_profiles(
    value: str | None,
) -> tuple[CustomEndpointProfile, ...]:
    """Parse a persisted custom-endpoint registry without exposing credentials."""
    if value is None:
        return ()
    if not isinstance(value, str):
        raise CustomEndpointError("Custom endpoint registry must be a JSON array.")

    try:
        raw_profiles = json.loads(value)
    except json.JSONDecodeError:
        raise CustomEndpointError(
            "Custom endpoint registry must be a valid JSON array."
        ) from None

    if not isinstance(raw_profiles, list):
        raise CustomEndpointError("Custom endpoint registry must be a JSON array.")

    profiles: list[CustomEndpointProfile] = []
    names: set[str] = set()
    for raw_profile in raw_profiles:
        profile = _parse_custom_endpoint_profile(raw_profile)
        if profile.name in names:
            raise CustomEndpointError(
                "Custom endpoint registry contains duplicate endpoint names."
            )
        names.add(profile.name)
        profiles.append(profile)
    return tuple(profiles)


def serialize_custom_endpoint_profiles(
    profiles: Iterable[CustomEndpointProfile],
) -> str:
    """Serialize custom endpoint profiles as deterministic compact JSON."""
    normalized_profiles: list[CustomEndpointProfile] = []
    try:
        for profile in profiles:
            if not isinstance(profile, CustomEndpointProfile):
                raise CustomEndpointError(
                    "Custom endpoint registry must contain endpoint profiles."
                )
            normalized_profiles.append(
                _parse_custom_endpoint_profile(
                    {
                        "name": profile.name,
                        "base_url": profile.base_url,
                        "api_key": profile.api_key,
                    }
                )
            )
    except TypeError:
        raise CustomEndpointError(
            "Custom endpoint registry must contain endpoint profiles."
        ) from None

    names: set[str] = set()
    for profile in normalized_profiles:
        if profile.name in names:
            raise CustomEndpointError(
                "Custom endpoint registry contains duplicate endpoint names."
            )
        names.add(profile.name)

    return json.dumps(
        [
            {
                "name": profile.name,
                "base_url": profile.base_url,
                "api_key": profile.api_key,
            }
            for profile in normalized_profiles
        ],
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _parse_custom_endpoint_profile(value: object) -> CustomEndpointProfile:
    """Validate and normalize one persisted custom-endpoint profile."""
    if not isinstance(value, dict) or set(value) != {
        "name",
        "base_url",
        "api_key",
    }:
        raise CustomEndpointError(
            "Each custom endpoint must include only name, base_url, and api_key."
        )

    return CustomEndpointProfile(
        name=normalize_custom_model_prefix(value["name"]),
        base_url=normalize_openai_base_url(value["base_url"]),
        api_key=_validate_api_key(value["api_key"]),
    )


class _NoRedirectHandler(HTTPRedirectHandler):
    """Prevent urllib from following redirects during authenticated discovery."""

    def redirect_request(self, *_: object, **__: object) -> None:
        """Refuse every redirect request so credentials stay on the chosen origin."""
        return None


@cache
def _litellm_provider_prefixes() -> frozenset[str]:
    """Return the installed LiteLLM provider identifiers without eager imports."""
    from litellm.types.utils import LlmProviders

    return frozenset(provider.value for provider in LlmProviders)


def _is_loopback_hostname(hostname: str) -> bool:
    """Return whether a URL hostname resolves only to the local host."""
    if hostname.lower() == "localhost" or hostname.lower().endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def normalize_openai_base_url(value: str) -> str:
    """Return an absolute OpenAI-compatible base URL ending in ``/v1``.

    The custom endpoint contract deliberately limits URLs to a direct HTTP(S)
    origin and path. Userinfo, query strings, and fragments are not useful for
    LiteLLM's API base and would make authenticated discovery unsafe.
    """
    if not isinstance(value, str):
        raise CustomEndpointError(
            "Custom endpoint URL must be a non-empty HTTP(S) URL."
        )

    candidate = value.strip()
    if not candidate:
        raise CustomEndpointError(
            "Custom endpoint URL must be a non-empty HTTP(S) URL."
        )

    try:
        parsed = urlsplit(candidate)
        hostname, _port = parsed.hostname, parsed.port
    except ValueError:
        raise CustomEndpointError(
            "Custom endpoint URL must be a valid HTTP(S) URL."
        ) from None

    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "?" in candidate
        or "#" in candidate
    ):
        raise CustomEndpointError(
            "Custom endpoint URL must be an absolute HTTP(S) URL without "
            "credentials, query parameters, or fragments."
        )
    if parsed.scheme.lower() == "http" and not _is_loopback_hostname(hostname):
        raise CustomEndpointError(
            "Custom endpoint URL must use HTTPS unless its host is loopback."
        )

    path = parsed.path.rstrip("/")
    if not path.endswith("/v1"):
        path = f"{path}/v1"

    return urlunsplit((parsed.scheme.lower(), parsed.netloc, path, "", ""))


def normalize_custom_model_prefix(value: str) -> str:
    """Return a safe lowercase custom-model prefix from a configured name."""
    if (
        not isinstance(value, str)
        or re.fullmatch(CUSTOM_LLM_NAME_PATTERN, value) is None
    ):
        raise CustomEndpointError(
            "Custom endpoint name must contain only letters, digits, "
            "underscores, or hyphens."
        )
    normalized = value.lower()
    if normalized in _litellm_provider_prefixes():
        raise CustomEndpointError(
            "Custom endpoint name must not use a LiteLLM provider prefix."
        )
    return normalized


def _fetch_model_list_payload(base_url: str, api_key: str) -> list[dict[str, object]]:
    """Fetch and validate the raw `/v1/models` `data` array.

    Shared by model-ID discovery and pricing discovery so both parse the
    exact same response instead of issuing two requests.

    Redirects are refused so the bearer token is never forwarded to another
    origin. Failures intentionally omit upstream response bodies and secrets.
    """
    normalized_base_url = normalize_openai_base_url(base_url)
    _validate_api_key(api_key)
    request = Request(
        f"{normalized_base_url}/models",
        headers={
            "Accept": CUSTOM_ENDPOINT_DISCOVERY_ACCEPT_HEADER,
            "Authorization": f"Bearer {api_key}",
            **LLM_IDENTIFYING_HEADERS,
        },
        method="GET",
    )
    opener = build_opener(_NoRedirectHandler())

    try:
        with opener.open(
            request, timeout=CUSTOM_ENDPOINT_HTTP_TIMEOUT_SECONDS
        ) as response:
            raw_payload = response.read()
    except HTTPError as error:
        logger.warning(
            "Custom endpoint model discovery failed",
            error_type=type(error).__name__,
            error=_summarize_error(error),
        )
        if 300 <= error.code < 400:
            raise CustomEndpointError(
                "Custom endpoint redirected model discovery. "
                "Use the final endpoint URL."
            ) from None
        raise CustomEndpointError(
            f"Custom endpoint model discovery failed with HTTP {error.code}."
        ) from None
    except (URLError, TimeoutError, OSError) as error:
        logger.warning(
            "Custom endpoint model discovery failed",
            error_type=type(error).__name__,
            error=_summarize_error(error),
        )
        raise CustomEndpointError(
            "Could not reach the custom endpoint while discovering models."
        ) from None
    except Exception as error:
        logger.warning(
            "Custom endpoint model discovery failed",
            error_type=type(error).__name__,
            error=_summarize_error(error),
        )
        raise CustomEndpointError(
            "Could not reach the custom endpoint while discovering models."
        ) from None

    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (AttributeError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        raise CustomEndpointError(
            "Custom endpoint model discovery returned invalid JSON."
        ) from None

    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise CustomEndpointError(
            "Custom endpoint model discovery returned an invalid model list."
        )

    for model in payload["data"]:
        if not isinstance(model, dict):
            raise CustomEndpointError(
                "Custom endpoint model discovery returned an invalid model list."
            )

    return payload["data"]


def _extract_model_ids(models: list[dict[str, object]]) -> list[str]:
    """Validate and collect model ids from a `/v1/models` `data` array."""
    model_ids: list[str] = []
    for model in models:
        model_id = model.get("id")
        try:
            model_ids.append(_validate_model_id(model_id))
        except CustomEndpointError:
            raise CustomEndpointError(
                "Custom endpoint model discovery returned an invalid model list."
            ) from None
    return model_ids


def discover_openai_compatible_models(base_url: str, api_key: str) -> list[str]:
    """Fetch sorted, unique model IDs from an OpenAI-compatible endpoint."""
    models = _fetch_model_list_payload(base_url, api_key)
    model_ids = _extract_model_ids(models)

    if not model_ids:
        raise CustomEndpointError(
            "Custom endpoint model discovery returned no usable models."
        )

    return sorted(set(model_ids))


# Known field-name pairs for per-token USD pricing nested under a model
# entry's `pricing` object, tried in this order. Different gateways that
# embed live pricing in their OpenAI-compatible `/v1/models` response use
# different key names for the same (prompt cost, completion cost) pair:
#   - OpenRouter:         pricing.prompt / pricing.completion
#   - Vercel AI Gateway:  pricing.input / pricing.output
# Self-hosted servers (vLLM, Ollama, LM Studio) and gateways whose pricing
# lives behind a separate API (e.g. Portkey) simply have no `pricing` object
# here at all, so they fall through untouched -- same as today.
_NESTED_PRICING_FIELD_PAIRS: tuple[tuple[str, str], ...] = (
    ("prompt", "completion"),
    ("input", "output"),
)
# Fallback when pricing isn't nested under `pricing` but flattened directly
# onto the model entry, using LiteLLM's own cost-map naming convention
# (seen on some self-hosted LiteLLM-proxy-style servers).
_FLAT_PRICING_FIELD_PAIR = ("input_cost_per_token", "output_cost_per_token")


def _coerce_price(value: object) -> float | None:
    """Parse one pricing value (str or number), rejecting anything negative."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if math.isfinite(price) and price >= 0 else None


def _extract_model_pricing(model: dict[str, object]) -> tuple[float, float] | None:
    """Try each known pricing convention against one model entry."""
    raw_pricing = model.get("pricing")
    if isinstance(raw_pricing, dict):
        for prompt_key, completion_key in _NESTED_PRICING_FIELD_PAIRS:
            prompt_cost = _coerce_price(raw_pricing.get(prompt_key))
            completion_cost = _coerce_price(raw_pricing.get(completion_key))
            if prompt_cost is not None and completion_cost is not None:
                return (prompt_cost, completion_cost)

    input_key, output_key = _FLAT_PRICING_FIELD_PAIR
    prompt_cost = _coerce_price(model.get(input_key))
    completion_cost = _coerce_price(model.get(output_key))
    if prompt_cost is not None and completion_cost is not None:
        return (prompt_cost, completion_cost)
    return None


def _extract_all_pricing(
    models: list[dict[str, object]],
) -> dict[str, tuple[float, float]]:
    """Extract per-model pricing from a `/v1/models` `data` array.

    Tries several known real-world conventions (see
    `_NESTED_PRICING_FIELD_PAIRS` and `_FLAT_PRICING_FIELD_PAIR`) generically
    against any endpoint's response. Models with no recognizable pricing are
    silently skipped -- this never fails discovery, and callers should keep
    treating an absent entry as "unknown, estimate as $0" exactly like
    before this existed.
    """
    pricing: dict[str, tuple[float, float]] = {}
    for model in models:
        model_id = model.get("id")
        if not isinstance(model_id, str) or not model_id:
            continue
        model_pricing = _extract_model_pricing(model)
        if model_pricing is not None:
            pricing[model_id] = model_pricing
    return pricing


def discover_openai_compatible_model_pricing(
    base_url: str, api_key: str
) -> dict[str, tuple[float, float]]:
    """Fetch per-model (prompt, completion) USD-per-token pricing, when advertised.

    See `_extract_all_pricing` for the conventions tried and fallback
    behavior when an endpoint doesn't advertise pricing at all.
    """
    return _extract_all_pricing(_fetch_model_list_payload(base_url, api_key))


async def verify_openai_compatible_model(
    base_url: str,
    api_key: str,
    model_id: str,
) -> None:
    """Verify one selected model with a tiny, explicitly scoped LiteLLM call."""
    normalized_base_url = normalize_openai_base_url(base_url)
    _validate_api_key(api_key)
    validated_model_id = _validate_model_id(model_id)

    try:
        from litellm import acompletion

        await acompletion(
            model=f"openai/{validated_model_id}",
            messages=[
                {
                    "role": "system",
                    "content": CUSTOM_ENDPOINT_VERIFICATION_INSTRUCTIONS,
                },
                {"role": "user", "content": CUSTOM_ENDPOINT_VERIFICATION_PROMPT},
            ],
            max_tokens=CUSTOM_ENDPOINT_VERIFICATION_MAX_OUTPUT_TOKENS,
            num_retries=0,
            api_base=normalized_base_url,
            api_key=api_key,
            extra_headers=dict(LLM_IDENTIFYING_HEADERS),
        )
    except Exception as error:
        logger.warning(
            "Custom endpoint model verification failed",
            error_type=type(error).__name__,
            error=_summarize_error(error),
        )
        raise CustomEndpointError(
            "Custom endpoint model verification failed. "
            "Check the model, URL, and API key."
        ) from None


def discover_and_verify_model(
    base_url: str,
    api_key: str,
    model: str,
    *,
    endpoint_name: str | None = None,
) -> dict[str, tuple[float, float]]:
    """Confirm `model` is discoverable, verify it live, and return pricing.

    Shared by `notewise inference add|update` and the interactive config
    editor's custom-endpoint manager so all three apply the exact same
    safety check before a profile is ever saved. The returned pricing map
    (often empty -- see `_extract_all_pricing`) comes from the same single
    `/v1/models` request used to confirm `model` exists, so callers get it
    for free and can attach it to the saved profile.
    """
    models = _fetch_model_list_payload(base_url, api_key)
    model_ids = _extract_model_ids(models)
    if not model_ids:
        raise CustomEndpointError(
            "Custom endpoint model discovery returned no usable models."
        )
    if model not in model_ids:
        where = f" by endpoint {endpoint_name!r}" if endpoint_name else ""
        raise CustomEndpointError(f"Model {model!r} was not returned{where}.")

    import asyncio

    asyncio.run(verify_openai_compatible_model(base_url, api_key, model))
    return _extract_all_pricing(models)


def default_model_endpoint_match(
    current_config: dict[str, str], endpoint_name: str
) -> str | None:
    """Return the model id if DEFAULT_MODEL currently selects this endpoint.

    Shared by `notewise inference update|delete` (to pick a default model,
    and to block deleting an endpoint DEFAULT_MODEL still relies on) and the
    interactive config editor's custom-endpoint manager.
    """
    default_prefix, separator, default_model_id = current_config.get(
        "DEFAULT_MODEL", ""
    ).partition("/")
    if not separator or not default_model_id:
        return None
    if re.fullmatch(CUSTOM_LLM_NAME_PATTERN, default_prefix) is None:
        # Genuinely malformed, not just "a real provider" -- we can't safely
        # rule out a match, so fail closed and let the caller decide
        # (e.g. `inference delete` refuses rather than risk deleting an
        # endpoint DEFAULT_MODEL might still reference).
        raise CustomEndpointError(
            "Custom endpoint name must contain only letters, digits, "
            "underscores, or hyphens."
        )
    normalized_prefix = default_prefix.lower()
    if normalized_prefix in _litellm_provider_prefixes():
        # A real LiteLLM provider prefix (e.g. "gemini") can never be a
        # saved custom endpoint name -- not a match, not an error.
        return None
    if normalized_prefix != endpoint_name:
        return None
    return default_model_id


def _validate_api_key(value: str) -> str:
    """Validate that an explicit custom endpoint API key was provided."""
    if not isinstance(value, str) or not value.strip():
        raise CustomEndpointError("Custom endpoint API key is required.")
    return value


def _validate_model_id(value: object) -> str:
    """Validate a model ID without restricting valid provider-specific syntax."""
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise CustomEndpointError(
            "Custom endpoint model ID must be non-empty and cannot contain whitespace."
        )
    return value


__all__ = [
    "CustomEndpointProfile",
    "discover_openai_compatible_models",
    "normalize_custom_model_prefix",
    "normalize_openai_base_url",
    "parse_custom_endpoint_profiles",
    "serialize_custom_endpoint_profiles",
    "verify_openai_compatible_model",
]
