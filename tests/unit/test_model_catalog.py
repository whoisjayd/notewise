"""Tests for shared LiteLLM model catalog helpers."""

from __future__ import annotations

import json

from notewise.model_catalog import (
    classify_provider,
    get_model_metadata,
    is_setup_safe_model,
    iter_model_metadata_keys,
    load_model_snapshot,
    normalize_available_models,
    parse_model_snapshot,
)


def test_normalize_available_models_keeps_known_providers_and_sorts_unique_models():
    result = normalize_available_models(
        {
            "openai": ["gpt-4o", "", "gpt-4o-mini", "gpt-4o"],
            "unsupported": ["model"],
        }
    )

    assert result == {"openai": ["gpt-4o", "gpt-4o-mini"]}


def test_parse_model_snapshot_ignores_malformed_provider_entries():
    result = parse_model_snapshot(
        {
            "openai": ["gpt-4o", None, ""],
            "unknown": ["ignored"],
            123: ["ignored"],
            "gemini": "gemini-2.5-flash",
        }
    )

    assert result == {"openai": ["gpt-4o"]}


def test_load_model_snapshot_returns_empty_for_missing_or_invalid_file(tmp_path):
    missing_path = tmp_path / "missing.json"
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("not json", encoding="utf-8")

    assert load_model_snapshot(missing_path) == {}
    assert load_model_snapshot(invalid_path) == {}


def test_load_model_snapshot_reads_and_normalizes_valid_file(tmp_path):
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        json.dumps({"openai": ["gpt-4o-mini", "gpt-4o-mini"]}),
        encoding="utf-8",
    )

    assert load_model_snapshot(snapshot_path) == {"openai": ["gpt-4o-mini"]}


def test_metadata_lookup_uses_strip_safe_native_provider_aliases():
    metadata = {"gpt-4o-mini": {"litellm_provider": "openai"}}

    assert iter_model_metadata_keys("openai/gpt-4o-mini") == [
        "openai/gpt-4o-mini",
        "gpt-4o-mini",
    ]
    assert get_model_metadata("openai/gpt-4o-mini", metadata) == metadata["gpt-4o-mini"]


def test_metadata_lookup_keeps_non_native_gateway_model_names_intact():
    metadata = {"openrouter/openai/gpt-4o-mini": {"litellm_provider": "openrouter"}}

    assert iter_model_metadata_keys("openrouter/openai/gpt-4o-mini") == [
        "openrouter/openai/gpt-4o-mini"
    ]
    assert (
        get_model_metadata("openrouter/openai/gpt-4o-mini", metadata)
        == metadata["openrouter/openai/gpt-4o-mini"]
    )


def test_classify_provider_maps_litellm_provider_to_setup_provider():
    assert classify_provider({"litellm_provider": "cohere_chat"}) == "cohere"
    assert classify_provider({"litellm_provider": "unknown"}) is None
    assert classify_provider({"litellm_provider": None}) is None


def test_is_setup_safe_model_requires_text_model_metadata():
    assert is_setup_safe_model(
        "gpt-4o-mini",
        {
            "litellm_provider": "openai",
            "mode": "chat",
            "supported_output_modalities": ["text"],
        },
    )


def test_is_setup_safe_model_rejects_deprecated_non_text_or_excluded_models():
    base_metadata = {
        "litellm_provider": "openai",
        "mode": "chat",
        "supported_output_modalities": ["text"],
    }

    assert not is_setup_safe_model("gpt-4o-mini", {})
    assert not is_setup_safe_model(
        "gpt-4o-mini",
        {**base_metadata, "deprecation_date": "2025-01-01"},
    )
    assert not is_setup_safe_model("gpt-4o-audio", base_metadata)
    assert not is_setup_safe_model(
        "gpt-4o-mini",
        {**base_metadata, "mode": "embedding"},
    )
    assert not is_setup_safe_model(
        "gpt-4o-mini",
        {**base_metadata, "supported_output_modalities": ["text", "image"]},
    )


def test_is_setup_safe_model_applies_provider_specific_exclusions():
    assert not is_setup_safe_model(
        "chatgpt/gpt-5.1-codex",
        {
            "litellm_provider": "chatgpt",
            "mode": "responses",
            "supported_output_modalities": ["text"],
        },
    )
