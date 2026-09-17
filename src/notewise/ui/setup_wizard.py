"""Configuration wizard for notewise."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import structlog

from notewise._constants import (
    AUTH_TYPE_API_KEY,
    AUTH_TYPE_OAUTH_DEVICE,
    CUSTOM_LLM_ENDPOINTS_ENV_VAR,
    DEFAULT_MAX_CONCURRENT_VIDEOS,
    DEFAULT_OUTPUT_DIR,
    OAUTH_SETUP_RUN_PROMPT,
    PROVIDER_CONFIG,
    SETUP_EMPTY_MODEL_CATALOG_MESSAGE,
    SETUP_MODEL_SELECTION_PAGE_SIZE,
)
from notewise._constants import (
    LEGACY_CONFIG_KEYS as APP_LEGACY_CONFIG_KEYS,
)
from notewise.config import get_config_db_path
from notewise.errors import ConfigurationError
from notewise.logging import _is_sensitive_key
from notewise.model_catalog import (
    classify_provider,
    get_model_metadata,
    is_setup_safe_model,
    load_model_snapshot,
    normalize_available_models,
)
from notewise.storage import config_store
from notewise.utils import mask_secret


logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


if TYPE_CHECKING:
    from collections.abc import Iterable

    from rich.console import Console

    from notewise.llm.custom_endpoint import CustomEndpointProfile


class RunOAuthLoginProto(Protocol):
    """Callable signature for the lazily imported OAuth login helper."""

    def __call__(self, provider: str, *, console: Console | None = None) -> bool: ...


LEGACY_CONFIG_KEYS = set(APP_LEGACY_CONFIG_KEYS)
run_oauth_login: RunOAuthLoginProto | None = None
_CUSTOM_ENDPOINTS_CATEGORY = "Custom Endpoints"


def _load_oauth_dependencies() -> None:
    """Populate OAuth login helpers lazily."""
    global run_oauth_login

    if run_oauth_login is None:
        from notewise.ui.oauth_flow import run_oauth_login as _run_oauth_login

        run_oauth_login = _run_oauth_login


def _resolve_console(console: Console | None) -> Console:
    """Return the provided console or create a fresh one for this flow."""
    from rich.console import Console

    return console if console is not None else Console()


def _normalize_available_models(
    provider_models: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Normalize provider model lists from the LiteLLM catalog snapshot."""
    return normalize_available_models(provider_models)


def _load_bundled_model_snapshot() -> dict[str, list[str]]:
    """Load the packaged LiteLLM model catalog when it is available."""
    return load_model_snapshot()


def get_config_path() -> Path:
    """Get path to the config database."""
    return get_config_db_path()


def load_config(*, suppress_errors: bool = False) -> dict[str, str]:
    """Load existing configuration."""
    db_path = get_config_db_path()
    try:
        return config_store.load_config_db(db_path)
    except (OSError, sqlite3.Error) as error:
        if suppress_errors:
            return {}
        raise ConfigurationError(
            f"Failed to read configuration from {db_path}: {error}"
        ) from error


def save_config(
    new_config: dict[str, str],
    *,
    console: Console | None = None,
) -> None:
    """
    Save configuration, merging with existing keys.

    Args:
        new_config: Dictionary of new configuration values to merge/update.
    """
    active_console = _resolve_console(console)
    db_path = get_config_db_path()

    # update_config_db holds SQLite's write lock across the whole
    # read-modify-write cycle, so concurrent callers (e.g. two `notewise
    # inference add` invocations) cannot silently clobber each other's change.
    config_store.update_config_db(db_path, new_config, drop_keys=LEGACY_CONFIG_KEYS)

    active_console.print(
        f"\n[green]✓[/green] Configuration saved to: [cyan]{db_path}[/cyan]"
    )


def _masked_value_display(key: str, value: str | None) -> str:
    """Return the display string for one config value, masked if sensitive."""
    if value is None:
        return "[dim]not set[/dim]"
    if _is_sensitive_key(key):
        return mask_secret(value, suffix=" (set)")
    return value


def select_config_category(
    categories: dict[str, tuple[str, ...]],
    *,
    console: Console | None = None,
) -> str | None:
    """Prompt the user to pick a config category. Returns None to exit."""
    from rich.prompt import Prompt
    from rich.table import Table

    active_console = _resolve_console(console)
    names = list(categories)

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Category", style="cyan")
    table.add_column("Keys", style="dim", justify="right")
    for i, name in enumerate(names, 1):
        table.add_row(str(i), name, str(len(categories[name])))

    active_console.print("\n[bold cyan]Configuration Categories:[/bold cyan]\n")
    active_console.print(table)

    while True:
        choice = Prompt.ask("\nSelect category number (or 'q' to quit)").strip()
        if choice.lower() in ("q", "quit", "exit"):
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(names):
            return names[int(choice) - 1]
        active_console.print(
            "[red]Invalid choice. Enter a category number or 'q'.[/red]"
        )


def _verify_and_save_endpoint(
    console: Console,
    db_path: Path,
    profile: CustomEndpointProfile,
    model: str,
) -> bool:
    """Discover, verify, and persist one endpoint. Returns True on success."""
    import sqlite3
    from dataclasses import replace

    from notewise.errors import ConfigurationError, CustomEndpointError
    from notewise.llm.custom_endpoint import discover_and_verify_model

    try:
        pricing = discover_and_verify_model(
            profile.base_url, profile.api_key, model, endpoint_name=profile.name
        )
        config_store.upsert_custom_endpoint(
            db_path, replace(profile, model_pricing=pricing)
        )
    except (ConfigurationError, CustomEndpointError, OSError, sqlite3.Error) as error:
        console.print(f"[red]{error}[/red]")
        return False
    return True


def _select_endpoint_by_index(
    profiles: tuple[CustomEndpointProfile, ...],
    console: Console,
    action_label: str,
) -> CustomEndpointProfile | None:
    """Prompt for the # shown in the endpoint table. Returns None to cancel."""
    from rich.prompt import Prompt

    choice = Prompt.ask(
        f"\nSelect endpoint # to {action_label} (or 'c' to cancel)"
    ).strip()
    if choice.lower() in ("c", "cancel"):
        return None
    if choice.isdigit() and 1 <= int(choice) <= len(profiles):
        return profiles[int(choice) - 1]
    console.print(f"[red]Invalid choice. Enter a number 1-{len(profiles)}.[/red]")
    return None


def _select_or_enter_model(console: Console, base_url: str, api_key: str) -> str:
    """Offer to discover and list the endpoint's models, or take one by hand.

    `base_url`/`api_key` must already reflect the values this endpoint will
    actually be saved with (e.g. the new base URL when one was entered
    during an update, falling back to the existing one otherwise) so the
    discovered list matches what verification will run against.
    """
    from rich.prompt import Confirm, Prompt

    from notewise.errors import CustomEndpointError
    from notewise.llm.custom_endpoint import discover_openai_compatible_models

    if Confirm.ask("Select the model from the endpoint's list?", default=True):
        try:
            models = discover_openai_compatible_models(base_url, api_key)
        except CustomEndpointError as error:
            console.print(f"[yellow]Could not list models ({error}).[/yellow]")
            models = []

        if models:
            # Reuses the same paginated, search-filterable picker as the
            # setup wizard's provider model selection.
            return select_model(
                "custom_openai_compatible",
                {"custom_openai_compatible": models},
                console=console,
            )
        console.print("[yellow]No models discovered; enter one manually.[/yellow]")

    return Prompt.ask("Model ID returned by this endpoint").strip()


def _pick_model_and_save_endpoint(
    console: Console,
    db_path: Path,
    name: str,
    base_url: str,
    api_key: str,
    *,
    success_verb: str,
) -> None:
    """Shared tail of add/update: pick a model, then build, verify, and save.

    `name`/`base_url`/`api_key` must already be normalized/resolved by the
    caller (add collects them fresh; update merges new values over the
    existing profile) -- this only handles the part both flows share.
    """
    from notewise.errors import CustomEndpointError
    from notewise.llm.custom_endpoint import (
        CustomEndpointProfile,
        default_model_endpoint_match,
    )

    model = _select_or_enter_model(console, base_url, api_key)
    if not model:
        console.print("[red]A model ID is required.[/red]")
        return
    try:
        profile = CustomEndpointProfile(name=name, base_url=base_url, api_key=api_key)
    except CustomEndpointError as error:
        console.print(f"[red]{error}[/red]")
        return
    if not _verify_and_save_endpoint(console, db_path, profile, model):
        return
    console.print(f"[green]{success_verb} endpoint {profile.name!r}.[/green]")

    # Keep DEFAULT_MODEL pointed at this endpoint's current model: sync it
    # immediately (no prompt) whenever it already targets this endpoint, or
    # is unset, so a model swap during update takes effect right away.
    target = f"{name}/{model}"
    current_config = load_config(suppress_errors=True)
    current_default = current_config.get("DEFAULT_MODEL", "")
    if current_default == target:
        return
    matched_model = default_model_endpoint_match(current_config, name)
    if matched_model is not None or not current_default:
        save_config({"DEFAULT_MODEL": target}, console=console)


def run_custom_endpoint_manager(*, console: Console | None = None) -> None:
    """Interactively add, update, and delete saved custom endpoints.

    Mirrors `notewise inference add|update|delete`, so the interactive
    editor manages the same one-row-per-endpoint config.db table instead of
    exposing the CUSTOM_LLM_ENDPOINTS whole-registry override as one opaque
    JSON string to overwrite.
    """
    import sqlite3

    from rich.prompt import Confirm, Prompt
    from rich.table import Table

    from notewise.errors import CustomEndpointError
    from notewise.llm.custom_endpoint import (
        default_model_endpoint_match,
        normalize_custom_model_prefix,
        normalize_openai_base_url,
    )

    active_console = _resolve_console(console)
    db_path = get_config_db_path()

    while True:
        try:
            profiles = config_store.list_custom_endpoints(db_path)
        except sqlite3.Error as error:
            active_console.print(f"[red]{error}[/red]")
            return

        table = Table(
            show_header=True, header_style="bold magenta", title="Custom Endpoints"
        )
        table.add_column("#", style="dim", width=4)
        table.add_column("Name", style="bold cyan")
        table.add_column("Base URL")
        for i, profile in enumerate(profiles, 1):
            table.add_row(str(i), profile.name, profile.base_url)

        active_console.print("\n[bold cyan]Custom Endpoints:[/bold cyan]\n")
        active_console.print(
            table if profiles else "[dim]No saved endpoints yet.[/dim]"
        )

        action = (
            Prompt.ask("\n'a' to add, 'u' to update, 'd' to delete, or 'q' to quit")
            .strip()
            .lower()
        )

        if action in ("q", "quit", "exit"):
            return

        if action in ("a", "add"):
            name = Prompt.ask("Name for this endpoint").strip()
            base_url = Prompt.ask("Base URL").strip()
            api_key = Prompt.ask("API key", password=True).strip()
            if not (name and base_url and api_key):
                active_console.print(
                    "[red]Name, base URL, and API key are required.[/red]"
                )
                continue
            try:
                normalized_base_url = normalize_openai_base_url(base_url)
                normalized_name = normalize_custom_model_prefix(name)
            except CustomEndpointError as error:
                active_console.print(f"[red]{error}[/red]")
                continue

            _pick_model_and_save_endpoint(
                active_console,
                db_path,
                normalized_name,
                normalized_base_url,
                api_key,
                success_verb="Saved",
            )
            continue

        if action in ("u", "update"):
            if not profiles:
                active_console.print("[yellow]No endpoints to update.[/yellow]")
                continue
            existing = _select_endpoint_by_index(profiles, active_console, "update")
            if existing is None:
                continue
            normalized = existing.name

            active_console.print("[dim]Leave blank to keep the current value.[/dim]")
            new_base_url = Prompt.ask(
                f"Base URL [{existing.base_url}]", default=""
            ).strip()
            new_api_key = Prompt.ask(
                "API key (blank to keep current)", password=True, default=""
            ).strip()
            try:
                effective_base_url = (
                    normalize_openai_base_url(new_base_url)
                    if new_base_url
                    else existing.base_url
                )
            except CustomEndpointError as error:
                active_console.print(f"[red]{error}[/red]")
                continue
            effective_api_key = new_api_key or existing.api_key

            _pick_model_and_save_endpoint(
                active_console,
                db_path,
                normalized,
                effective_base_url,
                effective_api_key,
                success_verb="Updated",
            )
            continue

        if action in ("d", "delete"):
            if not profiles:
                active_console.print("[yellow]No endpoints to delete.[/yellow]")
                continue
            target_profile = _select_endpoint_by_index(
                profiles, active_console, "delete"
            )
            if target_profile is None:
                continue
            normalized = target_profile.name

            try:
                current_config = load_config()
            except ConfigurationError as error:
                active_console.print(f"[red]{error}[/red]")
                continue
            if default_model_endpoint_match(current_config, normalized) is not None:
                active_console.print(
                    f"[red]Cannot delete {normalized!r} while DEFAULT_MODEL "
                    "uses it.[/red]"
                )
                continue
            if not Confirm.ask(f"Delete endpoint {normalized!r}?", default=False):
                continue
            try:
                config_store.delete_custom_endpoint(db_path, normalized)
            except sqlite3.Error as error:
                active_console.print(f"[red]{error}[/red]")
                continue
            active_console.print(f"[green]Deleted endpoint {normalized!r}.[/green]")
            continue

        active_console.print("[red]Invalid choice. Enter 'a', 'u', 'd', or 'q'.[/red]")


def _select_default_model_interactively(console: Console) -> str | None:
    """Offer the same provider+model pickers `notewise setup` uses.

    Returns None when the user picks "add a new custom endpoint" (that
    needs the full setup/endpoint-manager flow, not a quick DEFAULT_MODEL
    edit) or when nothing could be selected.
    """
    import sqlite3

    from notewise.storage import config_store

    db_path = get_config_db_path()
    try:
        custom_profiles = config_store.list_custom_endpoints(db_path)
    except sqlite3.Error:
        custom_profiles = ()

    console.print("\n[cyan]Loading available models...[/cyan]")
    available_models = get_available_models(console=console)
    provider_key = select_provider(
        available_models, custom_profiles=custom_profiles, console=console
    )

    if provider_key == "custom_openai_compatible":
        console.print(
            "[yellow]Add a new endpoint from the Custom Endpoints "
            "category first.[/yellow]"
        )
        return None

    profile = next((p for p in custom_profiles if p.name == provider_key), None)
    if profile is None:
        return select_model(provider_key, available_models, console=console)

    model_id = _discover_and_verify_custom_endpoint(profile, console=console)
    if model_id is None:
        return None
    return f"{profile.name}/{model_id}"


def run_config_editor(*, console: Console | None = None) -> None:
    """Interactively browse and edit persisted config, grouped by category."""
    import sqlite3

    from pydantic import ValidationError as PydanticValidationError
    from rich.prompt import Prompt
    from rich.table import Table

    from notewise.config import (
        categorize_config_keys,
        format_settings_validation_error,
        validate_candidate_config,
    )
    from notewise.config import settings as app_settings
    from notewise.errors import CustomEndpointError
    from notewise.storage import config_store

    active_console = _resolve_console(console)
    categories = categorize_config_keys()

    if not categories:
        active_console.print("[yellow]No configurable keys are available.[/yellow]")
        return

    while True:
        category = select_config_category(categories, console=active_console)
        if category is None:
            active_console.print("[dim]Exiting config editor.[/dim]")
            return

        if category == _CUSTOM_ENDPOINTS_CATEGORY:
            # Saved endpoints live one-per-row in config.db, not as the
            # single CUSTOM_LLM_ENDPOINTS override key -- editing that raw
            # key as one opaque JSON string is unusable. Manage the real
            # rows with add/update/delete instead, exactly like `notewise
            # inference add|update|delete` does.
            run_custom_endpoint_manager(console=active_console)
            continue

        while True:
            try:
                current_config = load_config()
            except ConfigurationError as error:
                active_console.print(f"[red]{error}[/red]")
                return

            keys_in_category = categories[category]
            table = Table(show_header=True, header_style="bold magenta", title=category)
            table.add_column("#", style="dim", width=4)
            table.add_column("Key", style="bold cyan")
            table.add_column("Value")
            for i, key in enumerate(keys_in_category, 1):
                display = _masked_value_display(key, current_config.get(key))
                table.add_row(str(i), key, display)

            active_console.print(f"\n[bold cyan]{category}:[/bold cyan]\n")
            active_console.print(table)

            choice = Prompt.ask(
                "\nSelect key number to edit, 'b' for categories, or 'q' to quit"
            ).strip()
            if choice.lower() in ("q", "quit", "exit"):
                active_console.print("[dim]Exiting config editor.[/dim]")
                return
            if choice.lower() in ("b", "back"):
                break
            if not (choice.isdigit() and 1 <= int(choice) <= len(keys_in_category)):
                active_console.print(
                    "[red]Invalid choice. Enter a key number, 'b', or 'q'.[/red]"
                )
                continue

            selected_key = keys_in_category[int(choice) - 1]
            existing_value = current_config.get(selected_key)
            active_console.print(
                f"\n[bold]{selected_key}[/bold]: "
                f"{_masked_value_display(selected_key, existing_value)}"
            )

            action = (
                Prompt.ask(
                    "Set new value ('s'), unset ('u'), or cancel ('c')",
                    default="c",
                )
                .strip()
                .lower()
            )

            if action in ("u", "unset"):
                if existing_value is None:
                    active_console.print(f"[yellow]{selected_key} is not set.[/yellow]")
                    continue
                db_path = get_config_db_path()
                if config_store.remove_config_key(db_path, selected_key):
                    active_console.print(
                        f"[green]Removed {selected_key} from configuration.[/green]"
                    )
                    try:
                        app_settings.reload()
                    except PydanticValidationError as error:
                        active_console.print(
                            f"[red]{format_settings_validation_error(error)}[/red]"
                        )
                continue

            if action in ("s", "set"):
                if selected_key == "DEFAULT_MODEL":
                    new_value = _select_default_model_interactively(active_console)
                    if not new_value:
                        continue
                else:
                    new_value = Prompt.ask(
                        f"Enter value for {selected_key}",
                        password=_is_sensitive_key(selected_key),
                    )
                try:
                    candidate = {
                        **load_config(suppress_errors=True),
                        selected_key: new_value,
                    }
                    validate_candidate_config(candidate)
                except PydanticValidationError as error:
                    active_console.print(
                        f"[red]{format_settings_validation_error(error)}[/red]"
                    )
                    continue

                try:
                    save_config({selected_key: new_value}, console=active_console)
                except (
                    CustomEndpointError,
                    ConfigurationError,
                    OSError,
                    sqlite3.Error,
                ) as error:
                    active_console.print(f"[red]{error}[/red]")
                    continue

                try:
                    app_settings.reload()
                except PydanticValidationError as error:
                    active_console.print(
                        f"[red]{format_settings_validation_error(error)}[/red]"
                    )
                continue

            if action not in ("c", "cancel", ""):
                active_console.print(
                    f"[yellow]{action!r} was not understood; no changes made. "
                    "Use 's' to set, 'u' to unset, or 'c' to cancel.[/yellow]"
                )
            # Cancel (explicit 'c'/'cancel', or the default blank input)
            # returns to the key list without changes.


def show_current_config(*, console: Console | None = None) -> dict[str, str]:
    """Display the current config in a read-only, masked form."""
    from rich.table import Table

    active_console = _resolve_console(console)
    config_path = get_config_path()
    try:
        current_config = load_config()
    except ConfigurationError as error:
        active_console.print(f"[red]{error}[/red]")
        return {}

    if not current_config:
        active_console.print(
            f"[yellow]No configuration found at {config_path}.[/yellow]"
        )
        return {}

    table = Table(title="Current Configuration", border_style="cyan")
    table.add_column("Key", style="bold cyan", no_wrap=True)
    table.add_column("Value")

    for key in sorted(current_config):
        value = current_config[key]
        if _is_sensitive_key(key):
            value = mask_secret(value, suffix=" (set)")
        table.add_row(key, value)

    active_console.print(f"[dim]Config:[/dim] {config_path}")
    active_console.print(table)
    return current_config


def get_available_models(*, console: Console | None = None) -> dict[str, list[str]]:
    """Load setup-ready models from the bundled snapshot or LiteLLM metadata."""
    bundled_models = _load_bundled_model_snapshot()
    if bundled_models:
        return bundled_models

    return _load_litellm_models(console=console)


def _load_litellm_models(*, console: Console | None = None) -> dict[str, list[str]]:
    """Fetch available models from LiteLLM when the bundled snapshot is absent."""
    active_console = _resolve_console(console)
    try:
        from litellm import model_cost, model_list

        provider_models: dict[str, list[str]] = {}

        candidate_models = {*model_list, *model_cost}
        candidate_models.discard("sample_spec")

        for model in candidate_models:
            if not isinstance(model, str) or not model:
                continue
            metadata = _get_model_metadata(model, model_cost)
            provider = _classify_provider(metadata)
            if provider is None:
                continue
            if not _is_setup_safe_model(model, metadata):
                continue

            if provider not in provider_models:
                provider_models[provider] = []
            provider_models[provider].append(model)

        return _normalize_available_models(provider_models)

    except Exception as e:
        logger.warning(
            "setup_wizard.model_fetch_failed",
            error_type=type(e).__name__,
            exc_info=True,
        )
        active_console.print(
            f"[yellow]⚠ Could not fetch models from LiteLLM: {e}[/yellow]"
        )
        active_console.print("[yellow]Using fallback model list...[/yellow]")
        return _normalize_available_models({})


def _get_model_metadata(
    model: str,
    model_cost: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return normalized LiteLLM metadata for a model when available."""
    return get_model_metadata(model, model_cost)


def _classify_provider(metadata: dict[str, Any]) -> str | None:
    """Map a model to one of the setup providers using LiteLLM provider metadata."""
    return classify_provider(metadata)


def _is_setup_safe_model(model: str, metadata: dict[str, Any]) -> bool:
    """Return True when a model is safe to show in setup."""
    return is_setup_safe_model(model, metadata)


def _prompt_positive_int(
    prompt: str,
    default: str,
    *,
    console: Console | None = None,
) -> str:
    """Prompt until the user enters a positive integer string."""
    from rich.prompt import Prompt

    active_console = _resolve_console(console)
    while True:
        value = Prompt.ask(prompt, default=default).strip()
        if value.isdigit() and int(value) >= 1:
            return value
        active_console.print(
            "[red]Please enter a whole number greater than or equal to 1.[/red]"
        )


def select_provider(
    available_models: dict[str, list[str]],
    *,
    custom_profiles: Iterable[CustomEndpointProfile] = (),
    console: Console | None = None,
) -> str:
    """Interactively select a built-in or saved custom endpoint provider."""
    from rich.prompt import Prompt
    from rich.table import Table

    active_console = _resolve_console(console)
    profiles = tuple(custom_profiles)
    active_console.print("\n[bold cyan]Select LLM Provider:[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Provider", style="cyan")
    table.add_column("Models Available", style="dim")

    providers_list = [
        provider_key
        for provider_key in PROVIDER_CONFIG
        if provider_key in available_models
    ]
    providers_list.extend(profile.name for profile in profiles)
    providers_list = list(dict.fromkeys(providers_list))
    providers_list.append("custom_openai_compatible")

    profile_names = {profile.name for profile in profiles}
    for i, provider_key in enumerate(providers_list, 1):
        if provider_key == "custom_openai_compatible":
            table.add_row(
                str(i),
                "Add custom OpenAI-compatible endpoint",
                "Discover models",
            )
            continue
        if provider_key in profile_names:
            table.add_row(str(i), provider_key, "Custom endpoint")
            continue

        config_data = PROVIDER_CONFIG[provider_key]
        model_count = len(available_models.get(provider_key, []))
        table.add_row(str(i), config_data["name"], f"{model_count} models")

    active_console.print(table)
    active_console.print(f"\n[dim]Total providers: {len(providers_list)}[/dim]")

    while True:
        choice = Prompt.ask(
            "\nSelect provider",
            choices=[str(i) for i in range(1, len(providers_list) + 1)],
        )
        return providers_list[int(choice) - 1]


def _prompt_with_page_keys(console: Console, prompt: str) -> tuple[str, str | None]:
    """Read a line of input, but let Left/Right arrow keys page instantly.

    Returns `(text, page_signal)`: `page_signal` is `"left"`/`"right"` when
    an arrow key was pressed (no Enter needed; `text` is whatever had been
    typed so far), or `None` after a normal Enter-terminated line.

    Raw key reading needs a real interactive terminal, so this falls back
    to a plain `Prompt.ask` (page_signal always `None`) when stdin isn't a
    tty -- piped input, tests, and CI keep working exactly as before.
    """
    import sys

    from rich.prompt import Prompt

    if not sys.stdin.isatty():
        return Prompt.ask(prompt).strip(), None

    import readchar

    console.print(prompt, end=": ")
    buffer: list[str] = []
    while True:
        key = readchar.readkey()
        if key == readchar.key.LEFT:
            console.print()
            return "".join(buffer), "left"
        if key == readchar.key.RIGHT:
            console.print()
            return "".join(buffer), "right"
        if key in (readchar.key.ENTER, "\r", "\n"):
            console.print()
            return "".join(buffer), None
        if key == readchar.key.CTRL_C:
            raise KeyboardInterrupt
        if key in (readchar.key.BACKSPACE, "\x7f", "\x08"):
            if buffer:
                buffer.pop()
                console.print("\b \b", end="")
            continue
        if len(key) == 1 and key.isprintable():
            buffer.append(key)
            console.print(key, end="")


def select_model(
    provider_key: str,
    available_models: dict[str, list[str]],
    *,
    console: Console | None = None,
) -> str:
    """Interactive model selection."""
    from rich.table import Table

    active_console = _resolve_console(console)
    if provider_key == "custom_openai_compatible":
        provider_name = "Custom OpenAI-Compatible Endpoint"
    elif provider_key not in PROVIDER_CONFIG:
        provider_name = f"{provider_key} custom endpoint"
    else:
        provider_name = PROVIDER_CONFIG[provider_key]["name"]
    models = available_models.get(provider_key, [])

    if not models:
        active_console.print(f"[yellow]No models found for {provider_name}[/yellow]")
        return f"{provider_key}/default"

    active_console.print(f"\n[bold cyan]Select {provider_name} Model:[/bold cyan]\n")
    active_console.print(f"[dim]Showing {len(models)} available models[/dim]\n")

    page_size = SETUP_MODEL_SELECTION_PAGE_SIZE
    current_page = 0
    filtered_models = models
    search_query = ""

    while True:
        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, len(filtered_models))
        page_models = filtered_models[start_idx:end_idx]

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim", width=4)
        table.add_column("Model", style="green")

        for i, model in enumerate(page_models, start_idx + 1):
            model_display = model
            if "flash" in model.lower() or "mini" in model.lower():
                model_display = f"{model} [dim](fast)[/dim]"
            elif (
                "pro" in model.lower()
                or "turbo" in model.lower()
                or "sonnet" in model.lower()
            ):
                model_display = f"{model} [dim](powerful)[/dim]"

            table.add_row(str(i), model_display)

        active_console.print(table)

        total_pages = max(1, (len(filtered_models) + page_size - 1) // page_size)
        if search_query:
            active_console.print(
                f"\n[dim]Search: '{search_query}' | Page {current_page + 1}/"
                f"{total_pages} | Showing {start_idx + 1}-{end_idx} of "
                f"{len(filtered_models)} matching models[/dim]"
            )
        else:
            active_console.print(
                f"\n[dim]Page {current_page + 1}/{total_pages} | "
                f"Showing {start_idx + 1}-{end_idx} of {len(filtered_models)} "
                f"models[/dim]"
            )

        hints = []
        if total_pages > 1:
            hints.append("'n'/'p' or Left/Right to navigate pages")
        hints.append("type text to search")
        if search_query:
            hints.append("'c' to clear search")
        active_console.print(f"[dim]{', '.join(hints).capitalize()}[/dim]")

        choice, page_signal = _prompt_with_page_keys(
            active_console, "\nSelect model (number, search text, or n/p/c)"
        )
        stripped = choice.strip()

        if (
            page_signal == "right" or stripped.lower() == "n"
        ) and current_page < total_pages - 1:
            current_page += 1
            active_console.clear()
            active_console.print(
                f"\n[bold cyan]Select {provider_name} Model:[/bold cyan]\n"
            )
            continue
        elif (page_signal == "left" or stripped.lower() == "p") and current_page > 0:
            current_page -= 1
            active_console.clear()
            active_console.print(
                f"\n[bold cyan]Select {provider_name} Model:[/bold cyan]\n"
            )
            continue
        elif stripped.lower() == "c" and search_query:
            filtered_models = models
            search_query = ""
            current_page = 0
            active_console.clear()
            active_console.print(
                f"\n[bold cyan]Select {provider_name} Model:[/bold cyan]\n"
            )
            continue
        elif stripped.isdigit() and 1 <= int(stripped) <= len(filtered_models):
            selected = filtered_models[int(stripped) - 1]

            if (
                provider_key == "gemini"
                and not selected.startswith("gemini/")
                and not selected.startswith("vertex_ai/")
            ):
                return f"gemini/{selected}"

            return selected
        elif stripped and not stripped.isdigit():
            query = stripped.lower()
            matches = [model for model in models if query in model.lower()]
            if not matches:
                active_console.print(
                    f"[yellow]No models match '{stripped}'. Try a different "
                    "search or 'c' to clear.[/yellow]"
                )
                continue
            filtered_models = matches
            search_query = stripped
            current_page = 0
            active_console.clear()
            active_console.print(
                f"\n[bold cyan]Select {provider_name} Model:[/bold cyan]\n"
            )
            continue

        active_console.print(
            "[red]Invalid choice. Enter a model number, search text, "
            "or n/p to navigate.[/red]"
        )


def get_api_key(
    provider_key: str,
    existing_key: str | None = None,
    *,
    console: Console | None = None,
) -> str:
    """Prompt for API key."""
    from rich.prompt import Confirm, Prompt

    active_console = _resolve_console(console)
    provider = PROVIDER_CONFIG[provider_key]

    active_console.print(
        f"\n[bold yellow]API Key Required:[/bold yellow] {provider['name']}"
    )
    active_console.print(
        f"[dim]Get your API key from:[/dim] "
        f"[link={provider['api_url']}]{provider['api_url']}[/link]\n"
    )

    if existing_key:
        masked = mask_secret(existing_key)
        use_existing = Confirm.ask(f"Use existing key ({masked})?", default=True)
        if use_existing:
            return existing_key

    while True:
        api_key = Prompt.ask("Enter your API key", password=True)
        if api_key and len(api_key) > 10:
            return api_key
        active_console.print("[red]Invalid API key. Please try again.[/red]")


def _discover_and_verify_custom_endpoint(
    profile: CustomEndpointProfile,
    *,
    console: Console,
) -> str | None:
    """Refresh a profile's model list and verify its selected model."""
    import asyncio

    from notewise.errors import CustomEndpointError
    from notewise.llm.custom_endpoint import (
        discover_openai_compatible_models,
        verify_openai_compatible_model,
    )

    console.print("\n[cyan]Discovering endpoint models...[/cyan]")
    try:
        models = discover_openai_compatible_models(profile.base_url, profile.api_key)
    except CustomEndpointError as error:
        console.print(f"[red]{error}[/red]")
        return None

    model_id = select_model(
        profile.name,
        {profile.name: models},
        console=console,
    )
    console.print("\n[cyan]Verifying selected model...[/cyan]")
    try:
        asyncio.run(
            verify_openai_compatible_model(profile.base_url, profile.api_key, model_id)
        )
    except CustomEndpointError as error:
        console.print(f"[red]{error}[/red]")
        return None

    return model_id


def _setup_custom_openai_compatible_endpoint(
    *,
    console: Console,
) -> tuple[str, CustomEndpointProfile] | None:
    """Collect, validate, discover, and verify a new custom endpoint."""
    from rich.prompt import Prompt

    from notewise.errors import CustomEndpointError
    from notewise.llm.custom_endpoint import (
        CustomEndpointProfile,
        normalize_custom_model_prefix,
        normalize_openai_base_url,
    )

    display_name = ""
    custom_model_prefix = ""
    while not custom_model_prefix:
        display_name = Prompt.ask("Endpoint display name").strip()
        try:
            custom_model_prefix = normalize_custom_model_prefix(display_name)
        except CustomEndpointError as error:
            console.print(f"[red]{error}[/red]")
    normalized_base_url = ""
    while not normalized_base_url:
        base_url = Prompt.ask("OpenAI-compatible base URL").strip()
        try:
            normalized_base_url = normalize_openai_base_url(base_url)
        except CustomEndpointError as error:
            console.print(f"[red]{error}[/red]")

    api_key = ""
    while not api_key:
        api_key = Prompt.ask("API key", password=True).strip()
        if not api_key:
            console.print("[red]API key cannot be empty.[/red]")

    profile = CustomEndpointProfile(
        name=custom_model_prefix,
        base_url=normalized_base_url,
        api_key=api_key,
    )
    model_id = _discover_and_verify_custom_endpoint(profile, console=console)
    if model_id is None:
        return None
    return f"{profile.name}/{model_id}", profile


def _replace_custom_endpoint_profile(
    profiles: tuple[CustomEndpointProfile, ...],
    replacement: CustomEndpointProfile,
) -> tuple[CustomEndpointProfile, ...]:
    """Replace a same-name profile in place or append a newly named profile."""
    if any(profile.name == replacement.name for profile in profiles):
        return tuple(
            replacement if profile.name == replacement.name else profile
            for profile in profiles
        )
    return (*profiles, replacement)


def run_setup_wizard(
    force: bool = False,
    console: Console | None = None,
) -> dict[str, str]:
    """Run interactive setup wizard."""
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt

    from notewise.errors import CustomEndpointError
    from notewise.llm.custom_endpoint import (
        parse_custom_endpoint_profiles,
        serialize_custom_endpoint_profiles,
    )

    active_console = _resolve_console(console)
    active_console.print(
        Panel(
            "[bold cyan]🎓 notewise Setup Wizard[/bold cyan]\n\n"
            "Configure your LLM provider and API keys\n"
            "[dim]Bundled LiteLLM model catalog for fast setup[/dim]",
            border_style="cyan",
            expand=False,
        )
    )

    current_config = load_config()

    if current_config and not force:
        active_console.print("\n[yellow]Existing configuration found.[/yellow]")
        reconfigure = Confirm.ask("Do you want to reconfigure?", default=False)
        if not reconfigure:
            active_console.print("[green]Using existing configuration.[/green]")
            return current_config

    try:
        custom_profiles = parse_custom_endpoint_profiles(
            current_config.get(CUSTOM_LLM_ENDPOINTS_ENV_VAR)
        )
    except CustomEndpointError as error:
        active_console.print(f"[red]{error}[/red]")
        return current_config

    active_console.print("\n[cyan]Loading available models...[/cyan]")
    available_models = get_available_models(console=active_console)
    if available_models:
        active_console.print(
            f"[green]✓ Found {sum(len(m) for m in available_models.values())} "
            f"models across {len(available_models)} providers[/green]"
        )
    else:
        active_console.print(f"[yellow]{SETUP_EMPTY_MODEL_CATALOG_MESSAGE}[/yellow]")
        active_console.print(
            "[yellow]Built-in providers are unavailable, but you can still "
            "configure a custom OpenAI-compatible endpoint.[/yellow]"
        )

    provider_key = select_provider(
        available_models,
        custom_profiles=custom_profiles,
        console=active_console,
    )
    custom_config: dict[str, str] = {}
    env_var: str | None = None
    api_key: str | None = None
    selected_profile = next(
        (profile for profile in custom_profiles if profile.name == provider_key),
        None,
    )

    if provider_key == "custom_openai_compatible":
        custom_endpoint = _setup_custom_openai_compatible_endpoint(
            console=active_console,
        )
        if custom_endpoint is None:
            return current_config
        model, profile = custom_endpoint
        custom_config[CUSTOM_LLM_ENDPOINTS_ENV_VAR] = (
            serialize_custom_endpoint_profiles(
                _replace_custom_endpoint_profile(custom_profiles, profile)
            )
        )
    elif selected_profile is not None:
        model_id = _discover_and_verify_custom_endpoint(
            selected_profile,
            console=active_console,
        )
        if model_id is None:
            return current_config
        model = f"{selected_profile.name}/{model_id}"
    else:
        model = select_model(provider_key, available_models, console=active_console)
        provider_info = PROVIDER_CONFIG[provider_key]
        configured_env_var = provider_info.get("env_var")
        env_var = configured_env_var if isinstance(configured_env_var, str) else None
        if provider_info.get("auth_type", AUTH_TYPE_API_KEY) == AUTH_TYPE_API_KEY and (
            env_var is not None
        ):
            existing_key = current_config.get(env_var)
            api_key = get_api_key(provider_key, existing_key, console=active_console)
        elif provider_info.get("auth_type") == AUTH_TYPE_OAUTH_DEVICE:
            active_console.print(
                "\n[bold yellow]OAuth Device Flow:[/bold yellow] "
                f"{provider_info['name']}"
            )
            active_console.print(
                "[dim]No API key is required for this provider. LiteLLM will show a "
                "device code on first use and store provider tokens locally. Existing "
                "API keys in config are preserved for future provider switches.[/dim]"
            )
            if Confirm.ask(OAUTH_SETUP_RUN_PROMPT, default=True):
                _load_oauth_dependencies()
                if run_oauth_login is not None and not run_oauth_login(
                    provider_key,
                    console=active_console,
                ):
                    active_console.print(
                        "[red]OAuth login failed or was cancelled. Setup stopped.[/red]"
                    )
                    return current_config

    active_console.print("\n[bold cyan]Output Directory:[/bold cyan]")
    default_output = str(Path.cwd() / Path(DEFAULT_OUTPUT_DIR))
    if "OUTPUT_DIR" in current_config:
        default_output = current_config["OUTPUT_DIR"]

    output_dir = Prompt.ask("Where should notes be saved?", default=default_output)

    active_console.print("\n[bold cyan]Concurrency:[/bold cyan]")
    default_concurrency = current_config.get(
        "MAX_CONCURRENT_VIDEOS",
        str(DEFAULT_MAX_CONCURRENT_VIDEOS),
    )
    concurrency = _prompt_positive_int(
        "Max concurrent videos to process?",
        default_concurrency,
        console=active_console,
    )

    new_config = {
        "DEFAULT_MODEL": model,
        "OUTPUT_DIR": output_dir,
        "MAX_CONCURRENT_VIDEOS": concurrency,
        **custom_config,
    }
    if env_var is not None and api_key:
        new_config[env_var] = api_key

    save_config(new_config, console=active_console)

    active_console.print("\n[bold green]✓ Setup complete![/bold green]")
    active_console.print(
        Panel(
            f"[dim]Selected model:[/dim] [cyan]{model}[/cyan]\n"
            f"[dim]Configuration saved to:[/dim] [cyan]{get_config_path()}[/cyan]\n\n"
            "[bold]Next Steps:[/bold]\n"
            'Run: [green]notewise process "URL"[/green]',
            title="🎉 Ready to go",
            border_style="green",
        )
    )

    current_config.update(new_config)
    for key in LEGACY_CONFIG_KEYS:
        current_config.pop(key, None)
    return current_config
