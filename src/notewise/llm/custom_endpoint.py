"""Discovery and validation for custom OpenAI-compatible endpoints."""

from __future__ import annotations

import ipaddress
import json
import math
import re
from dataclasses import dataclass, field
from functools import cache
from typing import TYPE_CHECKING
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import structlog

from notewise._constants import (
    CUSTOM_ENDPOINT_DISCOVERY_ACCEPT_HEADER,
    CUSTOM_ENDPOINT_HTTP_TIMEOUT_SECONDS,
    CUSTOM_ENDPOINT_OPERATION_PATH_SUFFIXES,
    CUSTOM_ENDPOINT_VERIFICATION_INSTRUCTIONS,
    CUSTOM_ENDPOINT_VERIFICATION_MAX_OUTPUT_TOKENS,
    CUSTOM_ENDPOINT_VERIFICATION_PROMPT,
    CUSTOM_ENDPOINT_VERSION_PATH,
    CUSTOM_ENDPOINT_VERSION_SEGMENT_PATTERN,
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


def _validated_base_url_parts(value: str) -> tuple[str, str, str]:
    """Validate an endpoint URL and return its `(scheme, netloc, path)`.

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

    return parsed.scheme.lower(), parsed.netloc.lower(), parsed.path


def _tidy_base_path(path: str) -> str:
    """Return the API-root path of a user-supplied endpoint path.

    Empty segments (duplicate and trailing slashes) are dropped, as is any
    pasted request path such as `/chat/completions` or `/models` -- those are
    endpoints a client calls, not the base to point a client at. The path is
    never emptied: a base URL with nothing left in it is not a base URL.
    """
    segments = [segment for segment in path.split("/") if segment]
    while len(segments) > 1:
        lowered = "/".join(segment.lower() for segment in segments)
        suffix = next(
            (
                candidate
                for candidate in CUSTOM_ENDPOINT_OPERATION_PATH_SUFFIXES
                if lowered == candidate or lowered.endswith(f"/{candidate}")
            ),
            None,
        )
        if suffix is None:
            break
        segments = segments[: -suffix.count("/") - 1]
    return "/".join(segments)


def clean_openai_base_url(value: str) -> str:
    """Return an absolute, tidied endpoint URL that keeps its own path.

    Applies the same validation and path cleanup as `normalize_openai_base_url`
    but never adds or removes a version segment. A base URL that has already
    been discovered, verified, or saved must survive a round trip through the
    config unchanged, so every caller downstream of resolution uses this.
    """
    scheme, netloc, path = _validated_base_url_parts(value)
    return urlunsplit((scheme, netloc, _tidy_base_path(path), "", ""))


def normalize_openai_base_url(value: str) -> str:
    """Return the base URL form a saved endpoint is configured with.

    A bare origin is never a usable OpenAI-compatible API base, so it gains
    the version segment. Every URL that already carries a path is kept
    exactly as written: discovery resolves a path that works as typed, and
    rewriting it here would silently repoint a working endpoint on the very
    next config read.
    """
    scheme, netloc, path = _validated_base_url_parts(value)
    tidied = _tidy_base_path(path)
    if tidied:
        return urlunsplit((scheme, netloc, tidied, "", ""))
    return urlunsplit((scheme, netloc, CUSTOM_ENDPOINT_VERSION_PATH, "", ""))


def versioned_openai_base_url(value: str) -> str:
    """Return the base URL with an explicit version segment appended.

    Unlike `normalize_openai_base_url` this also appends the segment to a path
    that lacks one (`https://host/api` -> `https://host/api/v1`). Use it when
    there is no discovery step to fall back on -- a single run's `--base-url`
    override -- and never to build a saved profile. A path already ending in a
    version segment (`v1`, `v1beta`, `v2`, in any case) is left as written.
    """
    scheme, netloc, path = _validated_base_url_parts(value)
    tidied = _tidy_base_path(path)
    final_segment = tidied.rsplit("/", 1)[-1]
    if tidied and re.fullmatch(
        CUSTOM_ENDPOINT_VERSION_SEGMENT_PATTERN, final_segment, re.IGNORECASE
    ):
        return urlunsplit((scheme, netloc, tidied, "", ""))
    return urlunsplit(
        (scheme, netloc, f"{tidied}{CUSTOM_ENDPOINT_VERSION_PATH}", "", "")
    )


def same_openai_base_url(left: str, right: str) -> bool:
    """Return whether two endpoint URLs address the same API base.

    Accepts a match whether either side spelled the version segment out
    (`https://host/v1`) or left it implicit (`https://host`), so a saved base
    URL still matches a caller that passes the origin it was derived from.
    """
    try:
        return clean_openai_base_url(left) == clean_openai_base_url(
            right
        ) or normalize_openai_base_url(left) == normalize_openai_base_url(right)
    except CustomEndpointError:
        return False


def _base_url_candidates(value: str) -> tuple[str, ...]:
    """Return the base URLs to try, in order.

    A bare origin has exactly one candidate -- the versioned form every
    OpenAI-compatible API uses -- so a resolved URL can never be saved in a
    shape that config parsing would rewrite. A URL with a path is tried
    exactly as typed first and only falls back to the versioned form when the
    endpoint rejects it.
    """
    as_typed = clean_openai_base_url(value)
    if not urlsplit(as_typed).path:
        return (normalize_openai_base_url(value),)
    versioned = versioned_openai_base_url(value)
    return (as_typed,) if as_typed == versioned else (as_typed, versioned)


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
    """Fetch the raw `/models` `data` array, or fail with a short reason.

    The base URL is used exactly as given: resolution is the caller's job, so
    a saved or already-discovered base is never rewritten here. Redirects are
    refused so the bearer token is never forwarded to another origin, and
    failures carry no upstream response body or secret -- the returned reason
    is a fragment the caller completes into one user-facing sentence.
    """
    cleaned_base_url = clean_openai_base_url(base_url)
    _validate_api_key(api_key)
    request = Request(
        f"{cleaned_base_url}/models",
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
                f"redirected to another origin (HTTP {error.code})"
            ) from None
        raise CustomEndpointError(f"HTTP {error.code}") from None
    except Exception as error:
        logger.warning(
            "Custom endpoint model discovery failed",
            error_type=type(error).__name__,
            error=_summarize_error(error),
        )
        raise CustomEndpointError("unreachable") from None

    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (AttributeError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        raise CustomEndpointError("returned invalid JSON") from None

    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise CustomEndpointError("returned an invalid model list")

    for model in payload["data"]:
        if not isinstance(model, dict):
            raise CustomEndpointError("returned an invalid model list")

    return payload["data"]


def _discover_model_list(base_url: str, api_key: str) -> list[dict[str, object]]:
    """Fetch the model list for one known-good base URL."""
    try:
        return _fetch_model_list_payload(base_url, api_key)
    except CustomEndpointError as reason:
        raise CustomEndpointError(
            f"Custom endpoint model discovery failed: {reason}."
        ) from None


def _resolve_model_list(
    value: str, api_key: str
) -> tuple[str, list[dict[str, object]]]:
    """Return the base URL that answered `/models` and the payload it returned.

    Candidates are tried in `base_url_candidates` order and the first that
    answers wins, so the winning URL can be saved and reused verbatim. When
    none answers, the error names every URL tried with the reason each failed.
    """
    attempts: list[str] = []
    for candidate in _base_url_candidates(value):
        try:
            return candidate, _fetch_model_list_payload(candidate, api_key)
        except CustomEndpointError as reason:
            attempts.append(f"{candidate} -> {reason}")
    raise CustomEndpointError(
        f"Custom endpoint model discovery failed. Tried {', '.join(attempts)}."
    )


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


def discover_openai_compatible_models(
    value: str, api_key: str
) -> tuple[str, list[str]]:
    """Resolve an endpoint base URL and return its sorted, unique model IDs."""
    resolved_base_url, models = _resolve_model_list(value, api_key)
    model_ids = _extract_model_ids(models)

    if not model_ids:
        raise CustomEndpointError(
            "Custom endpoint model discovery returned no usable models."
        )

    return resolved_base_url, sorted(set(model_ids))


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
    return _extract_all_pricing(_discover_model_list(base_url, api_key))


async def verify_openai_compatible_model(
    base_url: str,
    api_key: str,
    model_id: str,
) -> None:
    """Verify one selected model with a tiny, explicitly scoped LiteLLM call."""
    cleaned_base_url = clean_openai_base_url(base_url)
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
            api_base=cleaned_base_url,
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
    value: str,
    api_key: str,
    model: str,
    *,
    endpoint_name: str | None = None,
) -> tuple[str, dict[str, tuple[float, float]]]:
    """Resolve the base URL, confirm `model` is discoverable, verify it live.

    Shared by `notewise inference add|update` and the interactive config
    editor's custom-endpoint manager so all three apply the exact same
    safety check before a profile is ever saved. Returns the base URL that
    answered together with the pricing map captured from that same request
    (often empty -- see `_extract_all_pricing`), so callers save a profile
    whose base URL is known to work without paying for a second lookup.
    """
    resolved_base_url, models = _resolve_model_list(value, api_key)
    model_ids = _extract_model_ids(models)
    if not model_ids:
        raise CustomEndpointError(
            "Custom endpoint model discovery returned no usable models."
        )
    if model not in model_ids:
        where = f" by endpoint {endpoint_name!r}" if endpoint_name else ""
        raise CustomEndpointError(f"Model {model!r} was not returned{where}.")

    import asyncio

    asyncio.run(verify_openai_compatible_model(resolved_base_url, api_key, model))
    return resolved_base_url, _extract_all_pricing(models)


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
    "clean_openai_base_url",
    "discover_openai_compatible_models",
    "normalize_custom_model_prefix",
    "normalize_openai_base_url",
    "parse_custom_endpoint_profiles",
    "same_openai_base_url",
    "serialize_custom_endpoint_profiles",
    "verify_openai_compatible_model",
    "versioned_openai_base_url",
]
