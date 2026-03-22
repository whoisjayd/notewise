"""Application configuration via Pydantic v2 BaseSettings.

Load order (later overrides earlier):
1. Code defaults.
2. ~/.yt-study/config.env  (UserConfigSource).
3. Environment variables.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, cast

from pydantic import Field
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from yt_study._constants import (
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
    STATE_DIR_NAME,
)


_OPENAI_REASONING_MODEL = re.compile(r"(^|/)(o1|o3|o4)([-_/]|$)")
_NATIVE_PROVIDER_API_KEYS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "cohere": "COHERE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "openai": "OPENAI_API_KEY",
    "vertex": "GEMINI_API_KEY",
    "vertex_ai": "GEMINI_API_KEY",
    "xai": "XAI_API_KEY",
}
_UNSUPPORTED_GATEWAY_PREFIXES = frozenset({"azure", "openrouter", "vercel_ai_gateway"})
_LEGACY_IGNORED_KEYS: frozenset[str] = LEGACY_CONFIG_KEYS

_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GROQ_API_KEY",
        "XAI_API_KEY",
        "MISTRAL_API_KEY",
        "COHERE_API_KEY",
        "DEEPSEEK_API_KEY",
        "DEFAULT_MODEL",
        "OUTPUT_DIR",
        "MAX_CONCURRENT_VIDEOS",
        "YOUTUBE_REQUESTS_PER_MINUTE",
        "TEMPERATURE",
        "MAX_TOKENS",
        "YOUTUBE_COOKIE_FILE",
    }
)


def get_state_dir() -> Path:
    """Return the base directory for yt-study persistent state files."""
    override = os.getenv("YT_STUDY_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / STATE_DIR_NAME


def get_cache_db_path() -> Path:
    """Return the canonical global cache DB path."""
    return get_state_dir() / CACHE_DB_FILENAME


class UserConfigSource(PydanticBaseSettingsSource):
    """Load settings from ~/.yt-study/config.env (KEY=VALUE format)."""

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
        model_lower = model.strip().lower()
        if not model_lower:
            return None
        provider, sep, _ = model_lower.partition("/")
        if sep:
            if provider in _UNSUPPORTED_GATEWAY_PREFIXES:
                return None
            return _NATIVE_PROVIDER_API_KEYS.get(provider)
        if model_lower.startswith(("gemini", "vertex")):
            return "GEMINI_API_KEY"
        if model_lower.startswith(("gpt", "openai")) or _OPENAI_REASONING_MODEL.search(
            model_lower
        ):
            return "OPENAI_API_KEY"
        if model_lower.startswith(("claude", "anthropic")):
            return "ANTHROPIC_API_KEY"
        if model_lower.startswith("groq"):
            return "GROQ_API_KEY"
        if model_lower.startswith(("grok", "xai")):
            return "XAI_API_KEY"
        if model_lower.startswith("mistral"):
            return "MISTRAL_API_KEY"
        if model_lower.startswith(("cohere", "command")):
            return "COHERE_API_KEY"
        if model_lower.startswith("deepseek"):
            return "DEEPSEEK_API_KEY"
        return None

    def get_api_key_for_model(self, model: str) -> str | None:
        """Return the API key value for a given model."""
        var = self.get_api_key_name_for_model(model)
        return os.environ.get(var) if var else None


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
