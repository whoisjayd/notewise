"""Application configuration via Pydantic v2 BaseSettings.

Load order (later overrides earlier):
1. Code defaults.
2. ~/.notewise/config.env.
3. Environment variables.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, cast

import structlog
from pydantic import Field
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from notewise._constants import (
    AMBIENT_CREDENTIAL_PROVIDER_PREFIXES,
    CACHE_DB_FILENAME,
    CONFIG_FILENAME,
    DEFAULT_CHAPTER_MIN_DURATION,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_LANGUAGES,
    DEFAULT_MAX_CONCURRENT_CHAPTERS,
    DEFAULT_MAX_CONCURRENT_VIDEOS,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TEMPERATURE,
    DEFAULT_YOUTUBE_REQUESTS_PER_MINUTE,
    LEGACY_CONFIG_KEYS,
    LITELLM_MODELS_SNAPSHOT_FILENAME,
    OAUTH_DEVICE_PROVIDER_PREFIXES,
    OAUTH_PROVIDER_CONFIGS,
    OAUTH_TOKEN_DIR_ENV_VARS,
    OAUTH_TOKEN_DIR_NAMES,
    OAUTH_TOKEN_DIR_PARENT,
    PROVIDER_API_KEY_ENV_VARS,
    PROVIDER_AUTH_ENV_KEYS,
    PROVIDER_REQUIRED_ENV_VARS,
    STATE_DIR_NAME,
    UNSUPPORTED_MODEL_LIST_LIMIT,
    UNSUPPORTED_MODEL_MESSAGE,
)


logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)
_OPENAI_REASONING_MODEL = re.compile(r"(^|/)(o1|o3|o4)([-_/]|$)")
_LEGACY_IGNORED_KEYS: frozenset[str] = LEGACY_CONFIG_KEYS
_API_KEY_CONFIG_KEYS = frozenset(
    env_var for env_vars in PROVIDER_API_KEY_ENV_VARS.values() for env_var in env_vars
)
_MODEL_SNAPSHOT_CACHE: dict[str, tuple[str, ...]] | None = None

_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "DEFAULT_MODEL",
        "OUTPUT_DIR",
        "MAX_CONCURRENT_VIDEOS",
        "YOUTUBE_REQUESTS_PER_MINUTE",
        "TEMPERATURE",
        "MAX_TOKENS",
        "YOUTUBE_COOKIE_FILE",
    }
    | _API_KEY_CONFIG_KEYS
    | PROVIDER_AUTH_ENV_KEYS
)


def get_state_dir() -> Path:
    """Return the base directory for NoteWise persistent state files."""
    override = os.getenv("NOTEWISE_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / STATE_DIR_NAME


def get_cache_db_path() -> Path:
    """Return the canonical global cache DB path."""
    return get_state_dir() / CACHE_DB_FILENAME


def get_oauth_token_storage_paths() -> dict[str, Path]:
    """Return the notewise-scoped OAuth token directories by provider."""
    state_dir = get_state_dir()
    return {
        provider: state_dir / OAUTH_TOKEN_DIR_PARENT / directory
        for provider, directory in OAUTH_TOKEN_DIR_NAMES.items()
    }


def configure_oauth_token_storage() -> None:
    """Default LiteLLM OAuth token directories to the notewise state dir."""
    for provider, token_dir in get_oauth_token_storage_paths().items():
        env_var = OAUTH_TOKEN_DIR_ENV_VARS[provider]
        os.environ.setdefault(env_var, str(token_dir))


def _load_bundled_model_snapshot() -> dict[str, tuple[str, ...]]:
    """Load the bundled setup model snapshot for runtime preflight checks."""
    global _MODEL_SNAPSHOT_CACHE

    if _MODEL_SNAPSHOT_CACHE is not None:
        return _MODEL_SNAPSHOT_CACHE

    snapshot_path = Path(__file__).parent / "ui" / LITELLM_MODELS_SNAPSHOT_FILENAME
    try:
        with snapshot_path.open(encoding="utf-8") as snapshot_file:
            snapshot = json.load(snapshot_file)
    except (OSError, json.JSONDecodeError):
        logger.warning(
            "_load_bundled_model_snapshot failed to load or parse bundled snapshot",
            snapshot_path=str(snapshot_path),
            cache_variable="_MODEL_SNAPSHOT_CACHE",
            exc_info=True,
        )
        _MODEL_SNAPSHOT_CACHE = {}
        return _MODEL_SNAPSHOT_CACHE

    if not isinstance(snapshot, dict):
        logger.warning(
            "_load_bundled_model_snapshot ignored invalid bundled snapshot format",
            snapshot_path=str(snapshot_path),
            cache_variable="_MODEL_SNAPSHOT_CACHE",
            snapshot_type=type(snapshot).__name__,
        )
        _MODEL_SNAPSHOT_CACHE = {}
        return _MODEL_SNAPSHOT_CACHE

    normalized: dict[str, tuple[str, ...]] = {}
    for provider, models in snapshot.items():
        if not isinstance(provider, str) or not isinstance(models, list):
            logger.warning(
                "_load_bundled_model_snapshot skipped invalid provider entry",
                snapshot_path=str(snapshot_path),
                cache_variable="_MODEL_SNAPSHOT_CACHE",
                provider_type=type(provider).__name__,
                models_type=type(models).__name__,
            )
            continue
        normalized[provider] = tuple(
            model for model in models if isinstance(model, str) and model
        )
    _MODEL_SNAPSHOT_CACHE = normalized
    return _MODEL_SNAPSHOT_CACHE


class UserConfigSource(PydanticBaseSettingsSource):
    """Load settings from config.env in the active state directory."""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._cached_env_file: dict[str, str] | None = None

    def _load_env_file(self) -> dict[str, str]:
        """Parse the config.env file and return a key->value mapping."""
        if self._cached_env_file is not None:
            return self._cached_env_file

        path = get_state_dir() / CONFIG_FILENAME
        if not path.exists():
            self._cached_env_file = {}
            return self._cached_env_file
        result: dict[str, str] = {}
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key in _LEGACY_IGNORED_KEYS:
                    continue
                if key in _ALLOWED_KEYS:
                    if key not in os.environ:
                        os.environ[key] = value
                    result[key.lower()] = value
        except Exception:
            self._cached_env_file = {}
            return self._cached_env_file

        self._cached_env_file = result
        return self._cached_env_file

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        del field
        data = self._load_env_file()
        # Try field_name and alias lookups
        for lookup in (field_name, field_name.lower()):
            if lookup in data:
                return data[lookup], field_name, False
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return self._load_env_file()


class AppSettings(BaseSettings):
    """Global application configuration."""

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # LLM
    default_model: str = Field(DEFAULT_MODEL, alias="DEFAULT_MODEL")
    gemini_api_key: str | None = Field(None, alias="GEMINI_API_KEY")
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    groq_api_key: str | None = Field(None, alias="GROQ_API_KEY")
    xai_api_key: str | None = Field(None, alias="XAI_API_KEY")
    mistral_api_key: str | None = Field(None, alias="MISTRAL_API_KEY")
    cohere_api_key: str | None = Field(None, alias="COHERE_API_KEY")
    deepseek_api_key: str | None = Field(None, alias="DEEPSEEK_API_KEY")

    # Generation parameters
    temperature: float = Field(DEFAULT_TEMPERATURE, alias="TEMPERATURE", ge=0.0, le=1.0)
    max_tokens: int | None = Field(None, alias="MAX_TOKENS", gt=0)

    # Chunking (code defaults only; not exposed in config.env)
    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    chapter_generation_min_duration: int = DEFAULT_CHAPTER_MIN_DURATION

    # Concurrency
    max_concurrent_videos: int = Field(
        DEFAULT_MAX_CONCURRENT_VIDEOS, alias="MAX_CONCURRENT_VIDEOS", gt=0
    )
    max_concurrent_chapters: int = DEFAULT_MAX_CONCURRENT_CHAPTERS
    youtube_requests_per_minute: int = Field(
        DEFAULT_YOUTUBE_REQUESTS_PER_MINUTE, alias="YOUTUBE_REQUESTS_PER_MINUTE", gt=0
    )

    # Output
    default_output_dir: Path = Field(Path(DEFAULT_OUTPUT_DIR), alias="OUTPUT_DIR")

    # Transcript
    default_languages: list[str] = Field(
        default_factory=lambda: list(DEFAULT_LANGUAGES)
    )
    youtube_cookie_file: str | None = Field(None, alias="YOUTUBE_COOKIE_FILE")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        del dotenv_settings, file_secret_settings
        return (init_settings, env_settings, UserConfigSource(settings_cls))

    def model_post_init(self, __context: object) -> None:
        """Sync API keys back to os.environ for libraries that read env directly."""
        configure_oauth_token_storage()
        key_map = {
            "gemini_api_key": "GEMINI_API_KEY",
            "openai_api_key": "OPENAI_API_KEY",
            "anthropic_api_key": "ANTHROPIC_API_KEY",
            "groq_api_key": "GROQ_API_KEY",
            "xai_api_key": "XAI_API_KEY",
            "mistral_api_key": "MISTRAL_API_KEY",
            "cohere_api_key": "COHERE_API_KEY",
            "deepseek_api_key": "DEEPSEEK_API_KEY",
        }
        for attr, env_var in key_map.items():
            value = getattr(self, attr, None)
            if value:
                os.environ[env_var] = value
        if self.youtube_cookie_file:
            os.environ["YOUTUBE_COOKIE_FILE"] = self.youtube_cookie_file

    def get_state_dir(self) -> Path:
        return get_state_dir()

    def get_api_key_name_for_model(self, model: str) -> str | None:
        """Return the env var name for the API key required by a given model."""
        names = self.get_api_key_names_for_model(model)
        return names[0] if names else None

    def get_api_key_names_for_model(self, model: str) -> tuple[str, ...]:
        """Return all accepted env var names for the selected model provider."""
        model_lower = model.strip().lower()
        if not model_lower:
            return ()
        provider, sep, _ = model_lower.partition("/")
        if sep:
            if (
                provider in OAUTH_DEVICE_PROVIDER_PREFIXES
                or provider in AMBIENT_CREDENTIAL_PROVIDER_PREFIXES
            ):
                return ()
            return PROVIDER_API_KEY_ENV_VARS.get(provider, ())
        if model_lower.startswith(("gemini", "vertex")):
            return ("GEMINI_API_KEY",)
        if model_lower.startswith(("gpt", "openai")) or _OPENAI_REASONING_MODEL.search(
            model_lower
        ):
            return ("OPENAI_API_KEY",)
        if model_lower.startswith(("claude", "anthropic")):
            return ("ANTHROPIC_API_KEY",)
        if model_lower.startswith("groq"):
            return ("GROQ_API_KEY",)
        if model_lower.startswith(("grok", "xai")):
            return ("XAI_API_KEY",)
        if model_lower.startswith("mistral"):
            return ("MISTRAL_API_KEY",)
        if model_lower.startswith(("cohere", "command")):
            return ("COHERE_API_KEY",)
        if model_lower.startswith("deepseek"):
            return ("DEEPSEEK_API_KEY",)
        return ()

    def get_provider_prefix_for_model(self, model: str) -> str | None:
        """Return the normalized LiteLLM provider prefix for a model string."""
        model_lower = model.strip().lower()
        if not model_lower:
            return None
        provider, sep, _ = model_lower.partition("/")
        if sep:
            return provider
        return None

    def get_unsupported_model_message(self, model: str) -> str | None:
        """Return a user-facing message when a known setup model is unsupported."""
        normalized_model = model.strip().lower()
        if not normalized_model:
            return None

        snapshot = _load_bundled_model_snapshot()
        provider = self._get_snapshot_provider_for_model(normalized_model, snapshot)
        if provider is None:
            return None

        supported_models = snapshot.get(provider, ())
        if not supported_models or normalized_model in {
            supported_model.lower() for supported_model in supported_models
        }:
            return None

        listed_models = ", ".join(supported_models[:UNSUPPORTED_MODEL_LIST_LIMIT])
        if len(supported_models) > UNSUPPORTED_MODEL_LIST_LIMIT:
            listed_models = f"{listed_models}, ..."

        provider_config = OAUTH_PROVIDER_CONFIGS.get(provider, {})
        provider_label = provider_config.get("label", provider)
        return UNSUPPORTED_MODEL_MESSAGE.format(
            model=model,
            provider_label=provider_label,
            supported_models=listed_models,
        )

    def _get_snapshot_provider_for_model(
        self,
        normalized_model: str,
        snapshot: dict[str, tuple[str, ...]],
    ) -> str | None:
        """Return the setup snapshot provider that should validate a model."""
        provider = self.get_provider_prefix_for_model(normalized_model)
        if provider is not None:
            return provider if provider in snapshot else None

        for snapshot_provider, supported_models in snapshot.items():
            if normalized_model in {
                supported_model.lower() for supported_model in supported_models
            }:
                return snapshot_provider

        if normalized_model.startswith(
            ("gpt", "openai")
        ) or _OPENAI_REASONING_MODEL.search(normalized_model):
            return "openai" if "openai" in snapshot else None
        if normalized_model.startswith(("gemini", "vertex")):
            return "gemini" if "gemini" in snapshot else None
        if normalized_model.startswith(("claude", "anthropic")):
            return "anthropic" if "anthropic" in snapshot else None
        if normalized_model.startswith("groq"):
            return "groq" if "groq" in snapshot else None
        if normalized_model.startswith(("grok", "xai")):
            return "xai" if "xai" in snapshot else None
        if normalized_model.startswith("mistral"):
            return "mistral" if "mistral" in snapshot else None
        if normalized_model.startswith(("cohere", "command")):
            return "cohere" if "cohere" in snapshot else None
        if normalized_model.startswith("deepseek"):
            return "deepseek" if "deepseek" in snapshot else None
        return None

    def get_required_env_names_for_model(self, model: str) -> tuple[str, ...]:
        """Return non-API-key env vars required by a provider integration."""
        provider = self.get_provider_prefix_for_model(model)
        if provider is None:
            return ()
        return PROVIDER_REQUIRED_ENV_VARS.get(provider, ())

    def get_missing_config_names_for_model(self, model: str) -> tuple[str, ...]:
        """Return missing auth/config env names for a model provider."""
        missing: list[str] = []
        api_key_names = self.get_api_key_names_for_model(model)
        if api_key_names and not any(os.environ.get(name) for name in api_key_names):
            missing.append(" or ".join(api_key_names))
        for name in self.get_required_env_names_for_model(model):
            if not os.environ.get(name):
                missing.append(name)
        return tuple(missing)

    def get_api_key_for_model(self, model: str) -> str | None:
        """Return the API key value for a given model."""
        for var in self.get_api_key_names_for_model(model):
            value = os.environ.get(var)
            if value:
                return value
        return None


class _LazyAppSettings:
    """Lazy facade that preserves the historic module-level settings API."""

    def __init__(self) -> None:
        object.__setattr__(self, "_instance", None)

    def _get_instance(self) -> AppSettings:
        instance = cast(AppSettings | None, object.__getattribute__(self, "_instance"))
        if instance is None:
            instance = AppSettings()
            object.__setattr__(self, "_instance", instance)
        return instance

    def reload(self) -> AppSettings:
        """Rebuild the settings object from the current environment."""
        instance = AppSettings()
        object.__setattr__(self, "_instance", instance)
        return instance

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_instance(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_instance":
            object.__setattr__(self, name, value)
            return
        setattr(self._get_instance(), name, value)

    def __repr__(self) -> str:
        return repr(self._get_instance())


settings = _LazyAppSettings()
