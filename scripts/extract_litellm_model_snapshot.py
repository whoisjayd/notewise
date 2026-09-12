"""Extract notewise setup model snapshots from LiteLLM model metadata.

The input is LiteLLM's ``model_prices_and_context_window.json`` data. The
output is the provider -> model list consumed by the setup wizard.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.request import urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from notewise._constants import (  # noqa: E402
    LITELLM_MODEL_METADATA_FETCH_TIMEOUT_SECONDS,
    LITELLM_MODEL_METADATA_FIELDS,
    LITELLM_MODEL_METADATA_SOURCE_URL,
    LITELLM_MODELS_SNAPSHOT_FILENAME,
)
from notewise.model_catalog import (  # noqa: E402
    classify_provider,
    is_setup_safe_model,
    normalize_available_models,
)


if TYPE_CHECKING:
    from collections.abc import Sequence


DEFAULT_OUTPUT_PATH = (
    REPO_ROOT / "src" / "notewise" / "ui" / LITELLM_MODELS_SNAPSHOT_FILENAME
)


def build_snapshot(model_cost: dict[str, Any]) -> dict[str, list[str]]:
    """Build setup provider model lists from LiteLLM model metadata."""
    provider_models: dict[str, list[str]] = {}
    for model, metadata in model_cost.items():
        if model == "sample_spec" or not isinstance(model, str):
            continue
        if not isinstance(metadata, dict):
            continue

        provider = classify_provider(metadata)
        if provider is None:
            continue
        if not is_setup_safe_model(model, metadata):
            continue

        provider_models.setdefault(provider, []).append(model)

    return normalize_available_models(provider_models)


def build_metadata_snapshot(model_cost: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build a compact text-model metadata snapshot for future context logic."""
    models = build_snapshot(model_cost)
    selected_models = {
        model for provider_models in models.values() for model in provider_models
    }
    metadata_snapshot: dict[str, dict[str, Any]] = {}

    for model in sorted(selected_models):
        metadata = model_cost.get(model)
        if not isinstance(metadata, dict):
            continue
        metadata_snapshot[model] = {
            field: metadata[field]
            for field in LITELLM_MODEL_METADATA_FIELDS
            if field in metadata
        }

    return metadata_snapshot


def load_model_cost(
    source: str = LITELLM_MODEL_METADATA_SOURCE_URL,
) -> dict[str, Any]:
    """Load validated LiteLLM model metadata from the upstream source URL."""
    with urlopen(
        source,
        timeout=LITELLM_MODEL_METADATA_FETCH_TIMEOUT_SECONDS,
    ) as response:
        loaded = json.load(response)

    if not isinstance(loaded, dict):
        raise ValueError(f"Expected a JSON object from {source}")
    if not any(
        model != "sample_spec" and isinstance(model, str) and isinstance(metadata, dict)
        for model, metadata in loaded.items()
    ):
        raise ValueError(f"Expected usable model metadata from {source}")
    return loaded


def _validate_snapshot(snapshot: dict[str, list[str]]) -> None:
    """Reject an empty generation before it replaces the packaged catalog."""
    if not snapshot or not any(snapshot.values()):
        raise ValueError("LiteLLM metadata produced no setup-safe models.")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write deterministic JSON with a trailing newline."""
    content = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f"{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary_file:
            file_descriptor = -1
            temporary_file.write(content)
        temporary_path.replace(path)
    except BaseException:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        temporary_path.unlink(missing_ok=True)
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract notewise's LiteLLM setup model snapshot."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to write the provider model-list snapshot.",
    )
    parser.add_argument(
        "--metadata-output",
        type=Path,
        default=None,
        help="Optional path to write compact context-window metadata.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the snapshot extraction CLI."""
    args = parse_args(argv)
    model_cost = load_model_cost()
    snapshot = build_snapshot(model_cost)
    _validate_snapshot(snapshot)
    write_json(args.output, snapshot)

    if args.metadata_output is not None:
        write_json(args.metadata_output, build_metadata_snapshot(model_cost))

    model_count = sum(len(models) for models in snapshot.values())
    print(
        f"Wrote {model_count} models across {len(snapshot)} providers to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
