"""Drift checks for config and CLI documentation surfaces."""

from __future__ import annotations

import re
from inspect import signature
from pathlib import Path
from typing import Annotated, get_args, get_origin, get_type_hints

from typer.models import OptionInfo

from notewise._constants import (
    AUTH_TYPE_API_KEY,
    DEFAULT_MAX_CONCURRENT_VIDEOS,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TEMPERATURE,
    DEFAULT_YOUTUBE_REQUESTS_PER_MINUTE,
    OAUTH_TOKEN_DIR_ENV_VARS,
    PROVIDER_API_KEY_ENV_VAR_PROVIDERS,
    PROVIDER_CONFIG,
    PROVIDER_REQUIRED_ENV_VARS,
)
from notewise.cli.app import app


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read_repo_file(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _parse_common_config_table(markdown: str) -> dict[str, str]:
    """Return Key -> Default cells from the docs common-config table."""
    rows: dict[str, str] = {}
    in_table = False
    for line in markdown.splitlines():
        if line == "## Common config keys":
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0] in {"Key", "-----------------------------"}:
            continue
        key = cells[0].strip("`")
        rows[key] = cells[1]
    return rows


def _parse_env_example_keys() -> set[str]:
    keys: set[str] = set()
    for raw_line in _read_repo_file(".env.example").splitlines():
        line = raw_line.strip().removeprefix("#").strip()
        match = re.match(r"^([A-Z0-9_]+)=", line)
        if match:
            keys.add(match.group(1))
    return keys


def _process_option_declarations() -> set[str]:
    process_command = next(
        command
        for command in app.registered_commands
        if command.callback is not None and command.callback.__name__ == "process"
    )
    assert process_command.callback is not None
    hints = get_type_hints(process_command.callback, include_extras=True)
    declarations: set[str] = set()
    for parameter in signature(process_command.callback).parameters.values():
        annotation = hints.get(parameter.name)
        if get_origin(annotation) is not Annotated:
            continue
        for metadata in get_args(annotation)[1:]:
            if isinstance(metadata, OptionInfo):
                for declaration in (metadata.default, *metadata.param_decls):
                    if isinstance(declaration, str) and declaration.startswith("--"):
                        declarations.add(declaration)
    return declarations


def test_configuration_doc_common_defaults_match_source_constants():
    """User-facing config defaults should match the constants source of truth."""
    table = _parse_common_config_table(_read_repo_file("docs/config/configuration.mdx"))

    assert table == {
        "DEFAULT_MODEL": f"`{DEFAULT_MODEL}`",
        "OUTPUT_DIR": f"`{DEFAULT_OUTPUT_DIR}`",
        "MAX_CONCURRENT_VIDEOS": f"`{DEFAULT_MAX_CONCURRENT_VIDEOS}`",
        "YOUTUBE_REQUESTS_PER_MINUTE": f"`{DEFAULT_YOUTUBE_REQUESTS_PER_MINUTE}`",
        "TEMPERATURE": f"`{DEFAULT_TEMPERATURE}`",
        "MAX_TOKENS": "unset",
        "YOUTUBE_COOKIE_FILE": "unset",
        "ALLOW_UNLISTED_MODELS": "`false`",
    }


def test_env_example_lists_configurable_provider_env_vars():
    """Provider/auth env vars accepted from config.env should stay discoverable."""
    expected = (
        set(PROVIDER_API_KEY_ENV_VAR_PROVIDERS)
        | {
            env_var
            for env_vars in PROVIDER_REQUIRED_ENV_VARS.values()
            for env_var in env_vars
        }
        | set(OAUTH_TOKEN_DIR_ENV_VARS.values())
    )

    assert expected <= _parse_env_example_keys()


def test_provider_docs_list_setup_wizard_api_key_env_vars():
    """Provider docs should list credentials shown by the setup wizard."""
    providers_doc = _read_repo_file("docs/config/providers.mdx")
    setup_api_key_env_vars = {
        provider_config["env_var"]
        for provider_config in PROVIDER_CONFIG.values()
        if provider_config["auth_type"] == AUTH_TYPE_API_KEY
    }

    missing = [
        env_var
        for env_var in sorted(setup_api_key_env_vars)
        if f"`{env_var}`" not in providers_doc
    ]

    assert missing == []


def test_command_docs_process_flags_exist_in_cli_help():
    """Documented process flags should not drift after CLI option removals."""
    commands_doc = _read_repo_file("docs/operate/commands.mdx")
    important_flags_line = next(
        line
        for line in commands_doc.splitlines()
        if line.startswith("Important flags:")
    )
    documented_flags = re.findall(r"`(--[a-z0-9-]+)`", important_flags_line)

    process_options = _process_option_declarations()

    assert [flag for flag in documented_flags if flag not in process_options] == []
