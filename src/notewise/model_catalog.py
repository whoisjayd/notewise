"""Shared LiteLLM model catalog helpers for setup and preflight checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from notewise._constants import (
    ALLOWED_SETUP_MODEL_MODES,
    LITELLM_MODELS_SNAPSHOT_FILENAME,
    LITELLM_PROVIDER_TEXT_MODEL_EXCLUDED_MARKERS,
    LITELLM_TEXT_MODEL_EXCLUDED_MARKERS,
    NATIVE_PROVIDER_PREFIXES,
    PROVIDER_CONFIG,
)


logger = structlog.get_logger(__name__)


def bundled_model_snapshot_path() -> Path:
    """Return the packaged setup model snapshot path."""
    return Path(__file__).parent / "ui" / LITELLM_MODELS_SNAPSHOT_FILENAME


def normalize_available_models(
    provider_models: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Normalize provider model lists from LiteLLM catalog data."""
    return {
        provider: sorted({model for model in models if model})
        for provider, models in provider_models.items()
        if provider in PROVIDER_CONFIG
    }


def parse_model_snapshot(snapshot: object) -> dict[str, list[str]]:
    """Parse raw snapshot JSON into normalized setup model lists."""
    if not isinstance(snapshot, dict):
        return {}

    provider_models: dict[str, list[str]] = {}
    for provider, models in snapshot.items():
        if not isinstance(provider, str) or not isinstance(models, list):
            continue
        provider_models[provider] = [
            model for model in models if isinstance(model, str) and model
        ]

    return normalize_available_models(provider_models)


def load_model_snapshot(path: Path | None = None) -> dict[str, list[str]]:
    """Load and normalize the packaged LiteLLM setup model snapshot."""
    snapshot_path = path or bundled_model_snapshot_path()
    if not snapshot_path.exists():
        return {}

    try:
        with snapshot_path.open(encoding="utf-8") as snapshot_file:
            snapshot = json.load(snapshot_file)
    except (OSError, json.JSONDecodeError):
        logger.warning(
            "model_catalog.snapshot_load_failed",
            path=str(snapshot_path),
            exc_info=True,
        )
        return {}

    try:
        return parse_model_snapshot(snapshot)
    except Exception:
        logger.warning(
            "model_catalog.snapshot_parse_failed",
            path=str(snapshot_path),
            exc_info=True,
        )
        return {}


def get_model_metadata(
    model: str,
    model_cost: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return normalized LiteLLM metadata for a model when available."""
    for candidate in iter_model_metadata_keys(model):
        metadata = model_cost.get(candidate)
        if isinstance(metadata, dict):
            return metadata
    return {}


def iter_model_metadata_keys(model: str) -> list[str]:
    """Build safe metadata lookup keys without normalizing gateway models."""
    candidates = [model]
    provider_prefix, separator, remainder = model.partition("/")
    if separator and provider_prefix in NATIVE_PROVIDER_PREFIXES and remainder:
        candidates.append(remainder)
    return candidates


def classify_provider(metadata: dict[str, Any]) -> str | None:
    """Map a model to one of the setup providers using LiteLLM metadata."""
    litellm_provider = metadata.get("litellm_provider")
    if not isinstance(litellm_provider, str):
        return None

    for provider_key, provider_config in PROVIDER_CONFIG.items():
        if litellm_provider in provider_config.get("litellm_providers", []):
            return provider_key
    return None


def is_setup_safe_model(model: str, metadata: dict[str, Any]) -> bool:
    """Return True when a model is safe to show in setup."""
    if not metadata:
        return False
    if metadata.get("deprecation_date"):
        return False

    model_lower = model.lower()
    if any(marker in model_lower for marker in LITELLM_TEXT_MODEL_EXCLUDED_MARKERS):
        return False

    provider_prefix, separator, _ = model_lower.partition("/")
    provider_key = (
        provider_prefix
        if separator and provider_prefix in LITELLM_PROVIDER_TEXT_MODEL_EXCLUDED_MARKERS
        else classify_provider(metadata)
    )
    if provider_key is not None:
        provider_exclusions = LITELLM_PROVIDER_TEXT_MODEL_EXCLUDED_MARKERS.get(
            provider_key,
            (),
        )
        if any(marker in model_lower for marker in provider_exclusions):
            return False

    mode = metadata.get("mode")
    if not isinstance(mode, str) or mode not in ALLOWED_SETUP_MODEL_MODES:
        return False

    output_modalities = metadata.get("supported_output_modalities")
    if isinstance(output_modalities, list):
        normalized_modalities = {
            str(modality).lower() for modality in output_modalities
        }
        if normalized_modalities != {"text"}:
            return False

    return True
