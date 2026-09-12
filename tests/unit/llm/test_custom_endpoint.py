"""Tests for custom OpenAI-compatible endpoint support."""

from __future__ import annotations

import io
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError

import pytest

from notewise._constants import CUSTOM_ENDPOINT_HTTP_TIMEOUT_SECONDS
from notewise.errors import CustomEndpointError
from notewise.llm.custom_endpoint import (
    CustomEndpointProfile,
    discover_openai_compatible_models,
    normalize_custom_model_prefix,
    normalize_openai_base_url,
    parse_custom_endpoint_profiles,
    serialize_custom_endpoint_profiles,
    verify_openai_compatible_model,
)


class _FakeResponse:
    """Minimal context-managed HTTP response for discovery tests."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://models.example.test", "https://models.example.test/v1"),
        ("https://models.example.test/", "https://models.example.test/v1"),
        (
            "https://models.example.test/openai/",
            "https://models.example.test/openai/v1",
        ),
        ("https://models.example.test/v1/", "https://models.example.test/v1"),
    ],
)
def test_normalize_openai_base_url_appends_or_preserves_v1(
    value: str,
    expected: str,
) -> None:
    """Endpoint bases normalize to the LiteLLM-compatible ``/v1`` form."""
    assert normalize_openai_base_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "models.example.test",
        "ftp://models.example.test",
        "http://models.example.test",
        "https://user:password@models.example.test",
        "https://models.example.test/v1?tenant=example",
        "https://models.example.test/v1#models",
    ],
)
def test_normalize_openai_base_url_rejects_unsafe_urls(value: str) -> None:
    """Only direct absolute HTTP(S) endpoint URLs are accepted."""
    with pytest.raises(CustomEndpointError):
        normalize_openai_base_url(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://localhost:8000", "http://localhost:8000/v1"),
        ("http://127.0.0.1:8000", "http://127.0.0.1:8000/v1"),
        ("http://[::1]:8000", "http://[::1]:8000/v1"),
    ],
)
def test_normalize_openai_base_url_allows_loopback_http(
    value: str,
    expected: str,
) -> None:
    """Local endpoints may use HTTP without exposing credentials remotely."""
    assert normalize_openai_base_url(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("My_Custom-Endpoint", "my_custom-endpoint"),
        ("custom123", "custom123"),
    ],
)
def test_normalize_custom_model_prefix_lowercases_safe_names(
    value: str,
    expected: str,
) -> None:
    """Configured names become safe model-prefix segments."""
    assert normalize_custom_model_prefix(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "custom/name", "custom endpoint", "custom.endpoint", "openai", "ollama"],
)
def test_normalize_custom_model_prefix_rejects_unsafe_names(value: str) -> None:
    """Custom model prefixes cannot create an extra provider path segment."""
    with pytest.raises(CustomEndpointError):
        normalize_custom_model_prefix(value)


def test_parse_custom_endpoint_profiles_normalizes_and_preserves_order() -> None:
    """Registry profiles normalize names and URLs without reordering entries."""
    profiles = parse_custom_endpoint_profiles(
        '[{"name":"First_Endpoint","base_url":"https://first.example/","api_key":"first-key"},'
        '{"name":"second","base_url":"https://second.example/v1","api_key":"second-key"}]'
    )

    assert profiles == (
        CustomEndpointProfile(
            name="first_endpoint",
            base_url="https://first.example/v1",
            api_key="first-key",
        ),
        CustomEndpointProfile(
            name="second",
            base_url="https://second.example/v1",
            api_key="second-key",
        ),
    )


@pytest.mark.parametrize(
    "value",
    [
        "{",
        "{}",
        '[{"name":"endpoint","base_url":"https://endpoint.example/v1"}]',
        (
            '[{"name":"endpoint","base_url":"https://endpoint.example/v1",'
            '"api_key":"key","extra":true}]'
        ),
        '[{"name":"one","base_url":"https://one.example/v1","api_key":"key"},'
        '{"name":"ONE","base_url":"https://two.example/v1","api_key":"other-key"}]',
        (
            '[{"name":"endpoint","base_url":"https://endpoint.example/v1",'
            '"api_key":"   "}]'
        ),
    ],
)
def test_parse_custom_endpoint_profiles_rejects_invalid_registry(value: str) -> None:
    """Malformed schemas, duplicate names, and blank credentials are rejected."""
    with pytest.raises(CustomEndpointError):
        parse_custom_endpoint_profiles(value)


def test_parse_custom_endpoint_profiles_does_not_leak_profile_key() -> None:
    """Parser errors describe invalid input without echoing secret values."""
    secret = "registry-secret-value"

    with pytest.raises(CustomEndpointError) as raised:
        parse_custom_endpoint_profiles(
            f'[{{"name":"endpoint","base_url":"https://endpoint.example/v1",'
            f'"api_key":"{secret}","extra":true}}]'
        )

    assert secret not in str(raised.value)


def test_serialize_custom_endpoint_profiles_is_compact_and_deterministic() -> None:
    """Serializer validates profiles and emits stable one-line JSON."""
    profiles = (
        CustomEndpointProfile(
            name="First_Endpoint",
            base_url="https://first.example/",
            api_key="first-key",
        ),
        CustomEndpointProfile(
            name="second",
            base_url="https://second.example/v1",
            api_key="second-key",
        ),
    )

    serialized = serialize_custom_endpoint_profiles(profiles)

    assert serialized == (
        '[{"name":"first_endpoint","base_url":"https://first.example/v1","api_key":"first-key"},'
        '{"name":"second","base_url":"https://second.example/v1","api_key":"second-key"}]'
    )
    assert "\n" not in serialized
    assert serialize_custom_endpoint_profiles(profiles) == serialized


@pytest.mark.parametrize(
    "profiles",
    [
        (
            CustomEndpointProfile(
                name="one",
                base_url="https://one.example/v1",
                api_key="key",
            ),
            CustomEndpointProfile(
                name="ONE",
                base_url="https://two.example/v1",
                api_key="other-key",
            ),
        ),
        (
            CustomEndpointProfile(
                name="endpoint",
                base_url="https://endpoint.example/v1",
                api_key="",
            ),
        ),
    ],
)
def test_serialize_custom_endpoint_profiles_rejects_invalid_profiles(
    profiles: tuple[CustomEndpointProfile, ...],
) -> None:
    """Serializer rejects duplicate normalized names and blank credentials."""
    with pytest.raises(CustomEndpointError):
        serialize_custom_endpoint_profiles(profiles)


def test_discover_models_sends_bearer_auth_and_returns_sorted_unique_ids(
    mocker,
) -> None:
    """Discovery sends the supplied key only to the selected endpoint."""
    opener = MagicMock()
    opener.open.return_value = _FakeResponse(
        b'{"data": [{"id": "zeta"}, {"id": "alpha"}, {"id": "zeta"}]}'
    )
    mocker.patch("notewise.llm.custom_endpoint.build_opener", return_value=opener)

    models = discover_openai_compatible_models(
        "https://models.example.test", "test-api-key"
    )

    assert models == ["alpha", "zeta"]
    request = opener.open.call_args.args[0]
    assert request.full_url == "https://models.example.test/v1/models"
    assert request.get_header("Authorization") == "Bearer test-api-key"
    assert request.get_header("Accept") == "application/json"
    assert (
        opener.open.call_args.kwargs["timeout"] == CUSTOM_ENDPOINT_HTTP_TIMEOUT_SECONDS
    )


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b"[]",
        b'{"data": [{"id": ""}]}',
        b'{"data": [{"name": "missing-id"}]}',
        b'{"data": []}',
    ],
)
def test_discover_models_rejects_malformed_or_empty_payloads(
    mocker,
    payload: bytes,
) -> None:
    """Only non-empty OpenAI model lists with usable IDs can be selected."""
    opener = MagicMock()
    opener.open.return_value = _FakeResponse(payload)
    mocker.patch("notewise.llm.custom_endpoint.build_opener", return_value=opener)

    with pytest.raises(CustomEndpointError):
        discover_openai_compatible_models(
            "https://models.example.test/v1", "test-api-key"
        )


def test_discover_models_rejects_redirect_without_exposing_response_body(
    mocker,
) -> None:
    """Authenticated discovery must not follow a redirect to another origin."""
    opener = MagicMock()
    opener.open.side_effect = HTTPError(
        "https://models.example.test/v1/models",
        302,
        "Found",
        hdrs=None,
        fp=io.BytesIO(b"upstream-details"),
    )
    mocker.patch("notewise.llm.custom_endpoint.build_opener", return_value=opener)

    with pytest.raises(CustomEndpointError) as raised:
        discover_openai_compatible_models("https://models.example.test", "test-api-key")

    assert "redirect" in str(raised.value).lower()
    assert "upstream-details" not in str(raised.value)


def test_discover_models_logs_sanitized_failure_context(mocker) -> None:
    """Discovery failures retain a traceback for diagnostics without user leakage."""
    opener = MagicMock()
    opener.open.side_effect = URLError("unavailable")
    mocker.patch("notewise.llm.custom_endpoint.build_opener", return_value=opener)
    warning = mocker.patch("notewise.llm.custom_endpoint.logger.warning")

    with pytest.raises(CustomEndpointError):
        discover_openai_compatible_models("https://models.example.test", "test-key")

    warning.assert_called_once_with(
        "Custom endpoint model discovery failed",
        error_type="URLError",
        exc_info=True,
    )


async def test_verify_model_forwards_selected_model_base_and_key(mocker) -> None:
    """Verification uses an explicit, model-scoped LiteLLM request."""
    completion = mocker.patch("litellm.acompletion", new_callable=mocker.AsyncMock)

    await verify_openai_compatible_model(
        "https://models.example.test", "test-api-key", "provider/model-1"
    )

    completion.assert_awaited_once()
    kwargs = completion.call_args.kwargs
    assert kwargs["model"] == "openai/provider/model-1"
    assert kwargs["api_base"] == "https://models.example.test/v1"
    assert kwargs["api_key"] == "test-api-key"
    assert kwargs["max_tokens"] == 4
    assert kwargs["num_retries"] == 0
