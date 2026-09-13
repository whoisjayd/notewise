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
    default_model_endpoint_match,
    discover_and_verify_model,
    discover_openai_compatible_model_pricing,
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
    """Discovery failures log a redacted summary, not a raw traceback dump."""
    opener = MagicMock()
    opener.open.side_effect = URLError("unavailable")
    mocker.patch("notewise.llm.custom_endpoint.build_opener", return_value=opener)
    warning = mocker.patch("notewise.llm.custom_endpoint.logger.warning")

    with pytest.raises(CustomEndpointError):
        discover_openai_compatible_models("https://models.example.test", "test-key")

    warning.assert_called_once_with(
        "Custom endpoint model discovery failed",
        error_type="URLError",
        error="<urlopen error unavailable>",
    )


def test_discover_models_redacts_secrets_from_logged_failure(mocker) -> None:
    """A secret-shaped substring in the upstream error text must not reach logs."""
    opener = MagicMock()
    opener.open.side_effect = URLError("sk-abcdefghijklmnopqrstuvwx1234567890ABCD")
    mocker.patch("notewise.llm.custom_endpoint.build_opener", return_value=opener)
    warning = mocker.patch("notewise.llm.custom_endpoint.logger.warning")

    with pytest.raises(CustomEndpointError):
        discover_openai_compatible_models("https://models.example.test", "test-key")

    logged_error = warning.call_args.kwargs["error"]
    assert "sk-abcdefghijklmnopqrstuvwx1234567890ABCD" not in logged_error
    assert "exc_info" not in warning.call_args.kwargs


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
    assert kwargs["extra_headers"]["X-Title"] == "NoteWise"
    assert kwargs["extra_headers"]["HTTP-Referer"] == "https://notewise.click"


def test_discover_models_sends_identifying_headers(mocker) -> None:
    """Model discovery must identify notewise too, not just verification.

    Regression test: discovery previously sent only Accept/Authorization,
    so it never showed up as notewise on a gateway's usage dashboard even
    though generation and verification calls did.
    """
    opener = MagicMock()
    opener.open.return_value = _FakeResponse(b'{"data": [{"id": "vendor/model-1"}]}')
    mocker.patch("notewise.llm.custom_endpoint.build_opener", return_value=opener)

    discover_openai_compatible_models("https://models.example.test", "test-api-key")

    request = opener.open.call_args.args[0]
    assert request.get_header("X-title") == "NoteWise"
    assert request.get_header("Http-referer") == "https://notewise.click"


def test_discover_model_pricing_parses_openrouter_convention(mocker) -> None:
    """OpenRouter's `pricing.prompt`/`pricing.completion` convention."""
    opener = MagicMock()
    opener.open.return_value = _FakeResponse(
        b'{"data": [{"id": "vendor/model-1", '
        b'"pricing": {"prompt": "0.0000002", "completion": "0.0000008"}}]}'
    )
    mocker.patch("notewise.llm.custom_endpoint.build_opener", return_value=opener)

    pricing = discover_openai_compatible_model_pricing(
        "https://models.example.test", "test-api-key"
    )

    assert pricing == {"vendor/model-1": (0.0000002, 0.0000008)}


def test_discover_model_pricing_parses_vercel_ai_gateway_convention(mocker) -> None:
    """Vercel AI Gateway's `pricing.input`/`pricing.output` convention."""
    opener = MagicMock()
    opener.open.return_value = _FakeResponse(
        b'{"data": [{"id": "vendor/model-1", '
        b'"pricing": {"input": "0.00000012", "output": "0.00000024"}}]}'
    )
    mocker.patch("notewise.llm.custom_endpoint.build_opener", return_value=opener)

    pricing = discover_openai_compatible_model_pricing(
        "https://models.example.test", "test-api-key"
    )

    assert pricing == {"vendor/model-1": (0.00000012, 0.00000024)}


def test_discover_model_pricing_parses_litellm_flat_convention(mocker) -> None:
    """LiteLLM-style flat `input_cost_per_token`/`output_cost_per_token`."""
    opener = MagicMock()
    opener.open.return_value = _FakeResponse(
        b'{"data": [{"id": "vendor/model-1", '
        b'"input_cost_per_token": 0.0000015, "output_cost_per_token": 0.000006}]}'
    )
    mocker.patch("notewise.llm.custom_endpoint.build_opener", return_value=opener)

    pricing = discover_openai_compatible_model_pricing(
        "https://models.example.test", "test-api-key"
    )

    assert pricing == {"vendor/model-1": (0.0000015, 0.000006)}


def test_discover_model_pricing_skips_models_with_no_recognizable_pricing(
    mocker,
) -> None:
    """Self-hosted servers (vLLM, Ollama, ...) advertise no pricing at all --
    that must not raise or fabricate a cost, just skip the model.
    """
    opener = MagicMock()
    opener.open.return_value = _FakeResponse(
        b'{"data": [{"id": "meta-llama/Llama-3-8B-Instruct", '
        b'"object": "model", "owned_by": "vllm"}]}'
    )
    mocker.patch("notewise.llm.custom_endpoint.build_opener", return_value=opener)

    pricing = discover_openai_compatible_model_pricing(
        "https://models.example.test", "test-api-key"
    )

    assert pricing == {}


def test_discover_model_pricing_rejects_negative_or_malformed_values(
    mocker,
) -> None:
    """Malformed/negative pricing must be skipped, not crash or return junk."""
    opener = MagicMock()
    opener.open.return_value = _FakeResponse(
        b'{"data": ['
        b'{"id": "bad-negative", "pricing": {"prompt": "-1", "completion": "0.001"}},'
        b'{"id": "bad-type", "pricing": {"prompt": null, "completion": "0.001"}}'
        b"]}"
    )
    mocker.patch("notewise.llm.custom_endpoint.build_opener", return_value=opener)

    pricing = discover_openai_compatible_model_pricing(
        "https://models.example.test", "test-api-key"
    )

    assert pricing == {}


def test_default_model_endpoint_match_returns_model_id_for_matching_prefix() -> None:
    """DEFAULT_MODEL pointing at this endpoint's prefix returns its model id."""
    config = {"DEFAULT_MODEL": "office/vendor-model"}

    assert default_model_endpoint_match(config, "office") == "vendor-model"


def test_default_model_endpoint_match_returns_none_for_other_endpoint() -> None:
    """A DEFAULT_MODEL naming a different saved endpoint must not match."""
    config = {"DEFAULT_MODEL": "lab-server/vendor-model"}

    assert default_model_endpoint_match(config, "office") is None


def test_default_model_endpoint_match_returns_none_when_unset() -> None:
    """A missing/empty DEFAULT_MODEL must not match any endpoint."""
    assert default_model_endpoint_match({}, "office") is None


def test_default_model_endpoint_match_handles_builtin_provider_prefix() -> None:
    """A DEFAULT_MODEL using a real LiteLLM provider prefix (e.g. Gemini)
    must return None instead of raising -- a provider prefix can never be a
    saved custom endpoint name, so it's simply not a match, not an error.
    """
    config = {"DEFAULT_MODEL": "gemini/gemini-2.5-flash"}

    assert default_model_endpoint_match(config, "office") is None


def test_discover_and_verify_model_succeeds_when_model_is_listed(mocker) -> None:
    """A discovered model should be verified with a live request.

    `discover_and_verify_model` is synchronous (it drives verification via
    its own internal `asyncio.run`), so this test must stay a plain `def`,
    not `async def` -- calling it from an already-running event loop would
    raise.
    """
    mocker.patch(
        "notewise.llm.custom_endpoint._fetch_model_list_payload",
        return_value=[{"id": "vendor/model-1"}],
    )
    verify = mocker.patch(
        "notewise.llm.custom_endpoint.verify_openai_compatible_model",
        new_callable=mocker.AsyncMock,
    )

    discover_and_verify_model(
        "https://models.example.test/v1", "test-api-key", "vendor/model-1"
    )

    verify.assert_awaited_once_with(
        "https://models.example.test/v1", "test-api-key", "vendor/model-1"
    )


def test_discover_and_verify_model_rejects_model_missing_from_discovery(
    mocker,
) -> None:
    """A model absent from discovery must raise before any verification call."""
    mocker.patch(
        "notewise.llm.custom_endpoint._fetch_model_list_payload",
        return_value=[{"id": "vendor/model-1"}],
    )
    verify = mocker.patch(
        "notewise.llm.custom_endpoint.verify_openai_compatible_model",
        new_callable=mocker.AsyncMock,
    )

    with pytest.raises(CustomEndpointError, match="was not returned"):
        discover_and_verify_model(
            "https://models.example.test/v1",
            "test-api-key",
            "vendor/missing-model",
            endpoint_name="office",
        )

    verify.assert_not_awaited()
