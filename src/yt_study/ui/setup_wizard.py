"""Configuration wizard for yt-study."""

from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from yt_study._constants import (
    CONFIG_FILENAME,
    DEFAULT_MAX_CONCURRENT_VIDEOS,
    DEFAULT_OUTPUT_DIR,
)
from yt_study._constants import (
    LEGACY_CONFIG_KEYS as APP_LEGACY_CONFIG_KEYS,
)
from yt_study.config import get_state_dir


LEGACY_CONFIG_KEYS = set(APP_LEGACY_CONFIG_KEYS)


# API key configuration for different providers
PROVIDER_CONFIG: dict[str, dict[str, Any]] = {
    "gemini": {
        "name": "Google Gemini",
        "env_var": "GEMINI_API_KEY",
        "api_url": "https://aistudio.google.com/app/apikey",
        "keywords": ["gemini", "vertex"],
        "litellm_providers": ["gemini"],
    },
    "openai": {
        "name": "OpenAI (ChatGPT)",
        "env_var": "OPENAI_API_KEY",
        "api_url": "https://platform.openai.com/api-keys",
        "keywords": ["gpt", "openai", "o1", "o3", "o4"],
        "litellm_providers": ["openai"],
    },
    "anthropic": {
        "name": "Anthropic (Claude)",
        "env_var": "ANTHROPIC_API_KEY",
        "api_url": "https://console.anthropic.com/settings/keys",
        "keywords": ["claude", "anthropic"],
        "litellm_providers": ["anthropic"],
    },
    "groq": {
        "name": "Groq",
        "env_var": "GROQ_API_KEY",
        "api_url": "https://console.groq.com/keys",
        "keywords": ["groq"],
        "litellm_providers": ["groq"],
    },
    "xai": {
        "name": "xAI (Grok)",
        "env_var": "XAI_API_KEY",
        "api_url": "https://console.x.ai/",
        "keywords": ["grok", "xai"],
        "litellm_providers": ["xai"],
    },
    "mistral": {
        "name": "Mistral AI",
        "env_var": "MISTRAL_API_KEY",
        "api_url": "https://console.mistral.ai/api-keys/",
        "keywords": ["mistral"],
        "litellm_providers": ["mistral"],
    },
    "cohere": {
        "name": "Cohere",
        "env_var": "COHERE_API_KEY",
        "api_url": "https://dashboard.cohere.com/api-keys",
        "keywords": ["cohere", "command"],
        "litellm_providers": ["cohere_chat", "cohere"],
    },
    "deepseek": {
        "name": "DeepSeek",
        "env_var": "DEEPSEEK_API_KEY",
        "api_url": "https://platform.deepseek.com/api_keys",
        "keywords": ["deepseek"],
        "litellm_providers": ["deepseek"],
    },
}

CURATED_FALLBACK_MODELS: dict[str, list[str]] = {
    "gemini": [
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.5-flash-lite",
        "gemini/gemini-2.5-pro",
    ],
    "openai": [
        "gpt-4o-mini",
        "gpt-4o",
        "o3-mini",
    ],
    "anthropic": [
        "claude-haiku-4-5-20251001",
        "claude-sonnet-4-5-20250929",
        "claude-4-opus-20250514",
    ],
    "groq": [
        "groq/llama-3.1-8b-instant",
        "groq/llama-3.3-70b-versatile",
        "groq/meta-llama/llama-4-scout-17b-16e-instruct",
    ],
    "xai": [
        "xai/grok-3",
        "xai/grok-3-mini-latest",
        "xai/grok-4-0709",
    ],
    "mistral": [
        "mistral/mistral-small-latest",
        "mistral/mistral-medium-latest",
        "mistral/mistral-large-latest",
    ],
    "cohere": [
        "command-a-03-2025",
        "command-r-plus-08-2024",
        "command-r-08-2024",
    ],
    "deepseek": [
        "deepseek/deepseek-chat",
        "deepseek/deepseek-v3",
        "deepseek/deepseek-reasoner",
    ],
}

_ALLOWED_SETUP_MODEL_MODES = {"chat", "completion"}
_NATIVE_PROVIDER_PREFIXES = {
    "anthropic",
    "cohere",
    "deepseek",
    "gemini",
    "groq",
    "mistral",
    "openai",
    "xai",
}


def _resolve_console(console: Console | None) -> Console:
    """Return the provided console or create a fresh one for this flow."""
    return console if console is not None else Console()


def _strip_wrapped_quotes(value: str) -> str:
    """Remove one layer of matching quotes from config values."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def get_config_path() -> Path:
    """Get path to user config file."""
    config_dir = get_state_dir()
    config_dir.mkdir(exist_ok=True)
    return config_dir / CONFIG_FILENAME


def load_config() -> dict[str, str]:
    """Load existing configuration."""
    config_path = get_config_path()
    loaded_config = {}

    if config_path.exists():
        try:
            with config_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        loaded_config[key.strip()] = _strip_wrapped_quotes(
                            value.strip()
                        )
        except Exception:
            pass

    return loaded_config


def save_config(
    new_config: dict[str, str],
    *,
    console: Console | None = None,
) -> None:
    """
    Save configuration to file, preserving existing keys.

    Args:
        new_config: Dictionary of new configuration values to merge/update.
    """
    active_console = _resolve_console(console)
    config_path = get_config_path()
    current_config = load_config()

    current_config.update(new_config)
    for key in LEGACY_CONFIG_KEYS:
        current_config.pop(key, None)

    # Ensure file exists and set restrictive permissions (owner-only read/write)
    config_path.touch(exist_ok=True)
    config_path.chmod(0o600)

    with config_path.open("w", encoding="utf-8") as f:
        f.write("# yt-study Configuration\n")
        f.write("# Generated by yt-study setup wizard\n\n")

        priority_keys = [
            "DEFAULT_MODEL",
            "OUTPUT_DIR",
            "MAX_CONCURRENT_VIDEOS",
        ]
        for key in priority_keys:
            if key in current_config:
                f.write(f"{key}={current_config[key]}\n")

        for key, value in sorted(current_config.items()):
            if key not in priority_keys:
                f.write(f"{key}={value}\n")

    active_console.print(
        f"\n[green]✓[/green] Configuration saved to: [cyan]{config_path}[/cyan]"
    )


def get_available_models(*, console: Console | None = None) -> dict[str, list[str]]:
    """Fetch available models from LiteLLM."""
    active_console = _resolve_console(console)
    try:
        from litellm import model_cost, model_list

        provider_models: dict[str, list[str]] = {}

        for model in model_list:
            metadata = _get_model_metadata(model, model_cost)
            provider = _classify_provider(metadata)
            if provider is None:
                continue
            if not _is_setup_safe_model(model, metadata):
                continue

            if provider not in provider_models:
                provider_models[provider] = []
            provider_models[provider].append(model)

        for provider, fallback_models in CURATED_FALLBACK_MODELS.items():
            unique_models = sorted(set(provider_models.get(provider, [])))
            provider_models[provider] = unique_models or list(fallback_models)

        return provider_models

    except Exception as e:
        active_console.print(
            f"[yellow]⚠ Could not fetch models from LiteLLM: {e}[/yellow]"
        )
        active_console.print("[yellow]Using fallback model list...[/yellow]")
        return {
            provider: list(models)
            for provider, models in CURATED_FALLBACK_MODELS.items()
        }


def _get_model_metadata(
    model: str,
    model_cost: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return normalized LiteLLM metadata for a model when available."""
    for candidate in _iter_model_metadata_keys(model):
        metadata = model_cost.get(candidate)
        if isinstance(metadata, dict):
            return metadata
    return {}


def _iter_model_metadata_keys(model: str) -> list[str]:
    """Build safe metadata lookup keys without normalizing gateway models."""
    candidates = [model]
    provider_prefix, separator, remainder = model.partition("/")
    if separator and provider_prefix in _NATIVE_PROVIDER_PREFIXES and remainder:
        candidates.append(remainder)
    return candidates


def _classify_provider(metadata: dict[str, Any]) -> str | None:
    """Map a model to one of the setup providers using LiteLLM provider metadata."""
    litellm_provider = metadata.get("litellm_provider")
    if not isinstance(litellm_provider, str):
        return None

    for provider_key, provider_config in PROVIDER_CONFIG.items():
        if litellm_provider in provider_config.get("litellm_providers", []):
            return provider_key
    return None


def _is_setup_safe_model(_model: str, metadata: dict[str, Any]) -> bool:
    """Return True when a model is safe to show in setup."""
    if not metadata:
        return False
    if metadata.get("deprecation_date"):
        return False

    mode = metadata.get("mode")
    if not isinstance(mode, str) or mode not in _ALLOWED_SETUP_MODEL_MODES:
        return False

    output_modalities = metadata.get("supported_output_modalities")
    if isinstance(output_modalities, list):
        normalized_modalities = {
            str(modality).lower() for modality in output_modalities
        }
        if normalized_modalities != {"text"}:
            return False

    return True


def _prompt_positive_int(
    prompt: str,
    default: str,
    *,
    console: Console | None = None,
) -> str:
    """Prompt until the user enters a positive integer string."""
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
    console: Console | None = None,
) -> str:
    """Interactive provider selection."""
    active_console = _resolve_console(console)
    active_console.print("\n[bold cyan]Select LLM Provider:[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Provider", style="cyan")
    table.add_column("Models Available", style="dim")

    providers_list = []
    for prov_key, _prov_config in PROVIDER_CONFIG.items():
        if prov_key in available_models:
            providers_list.append(prov_key)

    for i, provider_key in enumerate(providers_list, 1):
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


def select_model(
    provider_key: str,
    available_models: dict[str, list[str]],
    *,
    console: Console | None = None,
) -> str:
    """Interactive model selection."""
    active_console = _resolve_console(console)
    provider_config = PROVIDER_CONFIG[provider_key]
    models = available_models.get(provider_key, [])

    if not models:
        active_console.print(
            f"[yellow]No models found for {provider_config['name']}[/yellow]"
        )
        return f"{provider_key}/default"

    active_console.print(
        f"\n[bold cyan]Select {provider_config['name']} Model:[/bold cyan]\n"
    )
    active_console.print(f"[dim]Showing {len(models)} available models[/dim]\n")

    page_size = 20
    current_page = 0

    while True:
        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, len(models))
        page_models = models[start_idx:end_idx]

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

        total_pages = (len(models) + page_size - 1) // page_size
        active_console.print(
            f"\n[dim]Page {current_page + 1}/{total_pages} | "
            f"Showing {start_idx + 1}-{end_idx} of {len(models)} "
            f"models[/dim]"
        )

        if total_pages > 1:
            active_console.print(
                "[dim]Type 'n' for next page, 'p' for previous page, "
                "or model number to select[/dim]"
            )

        choice = Prompt.ask("\nSelect model (or n/p for navigation)")

        if choice.lower() == "n" and current_page < total_pages - 1:
            current_page += 1
            active_console.clear()
            active_console.print(
                f"\n[bold cyan]Select {provider_config['name']} Model:[/bold cyan]\n"
            )
            continue
        elif choice.lower() == "p" and current_page > 0:
            current_page -= 1
            active_console.clear()
            active_console.print(
                f"\n[bold cyan]Select {provider_config['name']} Model:[/bold cyan]\n"
            )
            continue
        elif choice.isdigit() and 1 <= int(choice) <= len(models):
            selected = models[int(choice) - 1]

            if (
                provider_key == "gemini"
                and not selected.startswith("gemini/")
                and not selected.startswith("vertex_ai/")
            ):
                return f"gemini/{selected}"

            return selected

        active_console.print(
            "[red]Invalid choice. Enter a model number or use n/p to navigate.[/red]"
        )


def get_api_key(
    provider_key: str,
    existing_key: str | None = None,
    *,
    console: Console | None = None,
) -> str:
    """Prompt for API key."""
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
        masked = (
            f"{existing_key[:8]}...{existing_key[-4:]}"
            if len(existing_key) > 12
            else "***"
        )
        use_existing = Confirm.ask(f"Use existing key ({masked})?", default=True)
        if use_existing:
            return existing_key

    while True:
        api_key = Prompt.ask("Enter your API key", password=True)
        if api_key and len(api_key) > 10:
            return api_key
        active_console.print("[red]Invalid API key. Please try again.[/red]")


def run_setup_wizard(
    force: bool = False,
    console: Console | None = None,
) -> dict[str, str]:
    """Run interactive setup wizard."""
    active_console = _resolve_console(console)
    active_console.print(
        Panel(
            "[bold cyan]🎓 yt-study Setup Wizard[/bold cyan]\n\n"
            "Configure your LLM provider and API keys\n"
            "[dim]Powered by LiteLLM - 400+ models supported[/dim]",
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

    active_console.print("\n[cyan]Fetching available models from LiteLLM...[/cyan]")
    available_models = get_available_models(console=active_console)
    active_console.print(
        f"[green]✓ Found {sum(len(m) for m in available_models.values())} "
        f"models across {len(available_models)} providers[/green]"
    )

    provider_key = select_provider(available_models, console=active_console)
    model = select_model(provider_key, available_models, console=active_console)

    provider_info = PROVIDER_CONFIG[provider_key]
    existing_key = current_config.get(provider_info["env_var"])
    api_key = get_api_key(provider_key, existing_key, console=active_console)

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
        provider_info["env_var"]: api_key,
        "OUTPUT_DIR": output_dir,
        "MAX_CONCURRENT_VIDEOS": concurrency,
    }

    save_config(new_config, console=active_console)

    active_console.print("\n[bold green]✓ Setup complete![/bold green]")
    active_console.print(
        Panel(
            f"[dim]Selected model:[/dim] [cyan]{model}[/cyan]\n"
            f"[dim]Configuration saved to:[/dim] [cyan]{get_config_path()}[/cyan]\n\n"
            "[bold]Next Steps:[/bold]\n"
            'Run: [green]yt-study process "URL"[/green]',
            title="🎉 Ready to go",
            border_style="green",
        )
    )

    current_config.update(new_config)
    for key in LEGACY_CONFIG_KEYS:
        current_config.pop(key, None)
    return current_config
