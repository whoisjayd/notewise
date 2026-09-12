"""Behavioral tests for the LiteLLM snapshot extraction script."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest


if TYPE_CHECKING:
    from types import ModuleType


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "extract_litellm_model_snapshot.py"
)


@pytest.fixture
def extractor_module() -> ModuleType:
    """Load the executable script without relying on package layout."""
    spec = importlib.util.spec_from_file_location(
        "litellm_snapshot_extractor", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "upstream_metadata",
    [
        [],
        {"sample_spec": {}},
        {"gpt-4o-mini": "not metadata"},
        {"gpt-4o-mini": None},
    ],
)
def test_load_model_cost_rejects_non_model_metadata(
    extractor_module: ModuleType,
    tmp_path: Path,
    upstream_metadata: object,
) -> None:
    source = tmp_path / "upstream.json"
    source.write_text(json.dumps(upstream_metadata), encoding="utf-8")

    with pytest.raises(ValueError) as error:
        extractor_module.load_model_cost(source.as_uri())

    assert source.as_uri() in str(error.value)


def test_load_and_build_snapshot_preserve_usable_model_data(
    extractor_module: ModuleType,
    tmp_path: Path,
) -> None:
    source = tmp_path / "upstream.json"
    upstream_metadata = {
        "sample_spec": {},
        "gpt-4o-mini": {
            "litellm_provider": "openai",
            "mode": "chat",
            "supported_output_modalities": ["text"],
        },
    }
    source.write_text(json.dumps(upstream_metadata), encoding="utf-8")

    loaded = extractor_module.load_model_cost(source.as_uri())

    assert loaded == upstream_metadata
    assert extractor_module.build_snapshot(loaded) == {"openai": ["gpt-4o-mini"]}
    assert (
        extractor_module.build_metadata_snapshot(loaded)["gpt-4o-mini"][
            "litellm_provider"
        ]
        == "openai"
    )


def test_main_rejects_empty_snapshot_before_replacing_output(
    extractor_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "models.json"
    original = {"openai": ["gpt-4o-mini"]}
    output.write_text(json.dumps(original) + "\n", encoding="utf-8")
    original_contents = output.read_text(encoding="utf-8")
    non_setup_model_metadata = {
        "unavailable-model": {
            "litellm_provider": "unsupported-provider",
            "mode": "chat",
            "supported_output_modalities": ["text"],
        }
    }
    monkeypatch.setattr(
        extractor_module,
        "load_model_cost",
        lambda: non_setup_model_metadata,
    )

    with pytest.raises(ValueError):
        extractor_module.main(["--output", str(output)])

    assert output.read_text(encoding="utf-8") == original_contents
    assert json.loads(output.read_text(encoding="utf-8")) == original


def test_write_json_preserves_existing_valid_output_when_serialization_fails(
    extractor_module: ModuleType,
    tmp_path: Path,
) -> None:
    output = tmp_path / "models.json"
    original = {"openai": ["gpt-4o-mini"]}
    output.write_text(json.dumps(original) + "\n", encoding="utf-8")
    original_contents = output.read_text(encoding="utf-8")

    with pytest.raises(TypeError):
        extractor_module.write_json(output, {"openai": [object()]})

    assert output.read_text(encoding="utf-8") == original_contents
    assert json.loads(output.read_text(encoding="utf-8")) == original
