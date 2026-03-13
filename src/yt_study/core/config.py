"""Configuration management for yt-study."""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config_helpers import (
    default_youtube_oauth_token_file,
    is_valid_bool_setting,
    parse_bool_setting,
)


logger = logging.getLogger(__name__)
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
_UNSUPPORTED_GATEWAY_PREFIXES = {"azure", "openrouter", "vercel_ai_gateway"}


@dataclass
class Config:
    """
    Global configuration for the application.

    Manages loading settings from environment variables and config files.
    """

    # LLM Configuration
    default_model: str = "gemini/gemini-2.5-flash"
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    groq_api_key: str | None = None
    xai_api_key: str | None = None
    mistral_api_key: str | None = None
    cohere_api_key: str | None = None
    deepseek_api_key: str | None = None

    # LLM Generation Parameters
    temperature: float = 0.7
    max_tokens: int | None = None

    # Chunking Configuration
    chunk_size: int = 4000  # tokens
    chunk_overlap: int = 200  # tokens

    # Chapter Generation Configuration
    chapter_generation_min_duration: int = 3600  # seconds (1 hour)

    # Concurrency Configuration
    max_concurrent_videos: int = 5
    youtube_requests_per_minute: int = 10

    # YouTube Authentication
    youtube_use_oauth: bool = False
    youtube_save_oauth_token: bool = False
    youtube_oauth_token_file: Path | None = None
    youtube_auto_refresh_oauth_token: bool = True

    # Output Configuration
    default_output_dir: Path = Path("./output")

    # Transcript Configuration
    default_languages: list[str] = field(default_factory=lambda: ["en"])

    # Security: Allowed keys for environment injection
    ALLOWED_KEYS: set[str] = field(
        default_factory=lambda: {
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
            "YOUTUBE_USE_OAUTH",
            "YOUTUBE_SAVE_OAUTH_TOKEN",
            "YOUTUBE_OAUTH_TOKEN_FILE",
            "YOUTUBE_AUTO_REFRESH_OAUTH_TOKEN",
            "TEMPERATURE",
            "MAX_TOKENS",
        }
    )

    def __post_init__(self) -> None:
        """Load configuration from user config file and environment variables."""
        # First, try to load from user config file
        self._load_from_user_config()

        # Then load/override with environment variables
        self.gemini_api_key = os.getenv("GEMINI_API_KEY") or self.gemini_api_key
        self.openai_api_key = os.getenv("OPENAI_API_KEY") or self.openai_api_key
        self.anthropic_api_key = (
            os.getenv("ANTHROPIC_API_KEY") or self.anthropic_api_key
        )
        self.groq_api_key = os.getenv("GROQ_API_KEY") or self.groq_api_key
        self.xai_api_key = os.getenv("XAI_API_KEY") or self.xai_api_key
        self.mistral_api_key = os.getenv("MISTRAL_API_KEY") or self.mistral_api_key
        self.cohere_api_key = os.getenv("COHERE_API_KEY") or self.cohere_api_key
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY") or self.deepseek_api_key

        # Load default model and output dir from config
        env_model = os.getenv("DEFAULT_MODEL")
        if env_model:
            self.default_model = env_model

        env_output = os.getenv("OUTPUT_DIR")
        if env_output:
            self.default_output_dir = Path(env_output)

        self.max_concurrent_videos = self._load_positive_int_env(
            "MAX_CONCURRENT_VIDEOS",
            self.max_concurrent_videos,
        )

        self.youtube_requests_per_minute = self._load_positive_int_env(
            "YOUTUBE_REQUESTS_PER_MINUTE",
            self.youtube_requests_per_minute,
        )

        self.youtube_use_oauth = self._load_bool_env(
            "YOUTUBE_USE_OAUTH",
            self.youtube_use_oauth,
        )
        self.youtube_save_oauth_token = self._load_bool_env(
            "YOUTUBE_SAVE_OAUTH_TOKEN",
            self.youtube_save_oauth_token,
        )
        env_oauth_token_file = os.getenv("YOUTUBE_OAUTH_TOKEN_FILE")
        if env_oauth_token_file:
            self.youtube_oauth_token_file = Path(env_oauth_token_file).expanduser()

        self.youtube_auto_refresh_oauth_token = self._load_bool_env(
            "YOUTUBE_AUTO_REFRESH_OAUTH_TOKEN",
            self.youtube_auto_refresh_oauth_token,
        )

        if (
            self.youtube_use_oauth
            and self.youtube_save_oauth_token
            and self.youtube_oauth_token_file is None
        ):
            self.youtube_oauth_token_file = default_youtube_oauth_token_file()

        env_temperature = os.getenv("TEMPERATURE")
        if env_temperature:
            try:
                temp_value = float(env_temperature)
                if not (0 <= temp_value <= 1):
                    logger.warning(
                        f"TEMPERATURE out of range [0, 1]: {env_temperature}. "
                        f"Using default 0.7"
                    )

                else:
                    self.temperature = temp_value
            except ValueError:
                logger.warning(
                    f"Invalid TEMPERATURE value: {env_temperature}. Using default 0.7"
                )

        env_max_tokens = os.getenv("MAX_TOKENS")
        if env_max_tokens:
            try:
                # self.max_tokens = int(env_max_tokens)
                max_tokens_value = int(env_max_tokens)
                if max_tokens_value < 1:
                    logger.warning(
                        f"MAX_TOKENS must be >= 1: {env_max_tokens}. "
                        f"Setting to None (default)"
                    )

                else:
                    self.max_tokens = max_tokens_value

            except ValueError:
                logger.warning(
                    f"Invalid MAX_TOKENS value: {env_max_tokens}. "
                    f"Setting to None (default)"
                )

        self._sync_env_vars()

    def _load_positive_int_env(self, key: str, default: int) -> int:
        """
        Load a positive integer from environment.

        Returns the provided default when the variable is absent, non-numeric,
        or less than 1.
        """
        raw_value = os.getenv(key)
        if raw_value is None:
            return default

        try:
            parsed = int(raw_value)
        except ValueError:
            logger.warning(f"Invalid {key} value: {raw_value}. Using default {default}")
            return default

        if parsed < 1:
            logger.warning(f"{key} must be >= 1: {raw_value}. Using default {default}")
            return default

        return parsed

    def _load_bool_env(self, key: str, default: bool) -> bool:
        """
        Load a boolean from environment.

        Accepted truthy values: `1`, `true`, `yes`, `on`
        Accepted falsy values: `0`, `false`, `no`, `off`
        """
        raw_value = os.getenv(key)
        parsed = parse_bool_setting(raw_value, default)
        if not is_valid_bool_setting(raw_value):
            logger.warning(f"Invalid {key} value: {raw_value}. Using default {default}")
        return parsed

    def _load_from_user_config(self) -> None:
        """Load configuration from user's config file."""
        config_path = Path.home() / ".yt-study" / "config.env"

        if not config_path.exists():
            return

        try:
            with config_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip()

                        # Remove quotes if present
                        if (value.startswith('"') and value.endswith('"')) or (
                            value.startswith("'") and value.endswith("'")
                        ):
                            value = value[1:-1]

                        if key in self.ALLOWED_KEYS:
                            # Pre-populate env for consistency
                            if key not in os.environ:
                                os.environ[key] = value
                        else:
                            logger.warning(f"Ignoring unauthorized config key: {key}")

        except Exception as e:
            logger.warning(f"Failed to load config file: {e}")
            pass

    def _sync_env_vars(self) -> None:
        """Sync class attributes back to os.environ for libraries that expect them."""
        if self.gemini_api_key:
            os.environ["GEMINI_API_KEY"] = self.gemini_api_key
        if self.openai_api_key:
            os.environ["OPENAI_API_KEY"] = self.openai_api_key
        if self.anthropic_api_key:
            os.environ["ANTHROPIC_API_KEY"] = self.anthropic_api_key
        if self.groq_api_key:
            os.environ["GROQ_API_KEY"] = self.groq_api_key
        if self.xai_api_key:
            os.environ["XAI_API_KEY"] = self.xai_api_key
        if self.mistral_api_key:
            os.environ["MISTRAL_API_KEY"] = self.mistral_api_key
        if self.cohere_api_key:
            os.environ["COHERE_API_KEY"] = self.cohere_api_key
        if self.deepseek_api_key:
            os.environ["DEEPSEEK_API_KEY"] = self.deepseek_api_key

    def get_api_key_name_for_model(self, model: str) -> str | None:
        """Get the environment variable name for the API key required by a model."""
        model_lower = model.strip().lower()
        if not model_lower:
            return None

        provider_prefix, separator, remainder = model_lower.partition("/")
        if separator:
            if provider_prefix in _UNSUPPORTED_GATEWAY_PREFIXES:
                return None
            if provider_prefix in _NATIVE_PROVIDER_API_KEYS:
                return _NATIVE_PROVIDER_API_KEYS[provider_prefix]
            return None

        if model_lower.startswith("gemini") or model_lower.startswith("vertex"):
            return "GEMINI_API_KEY"
        elif (
            model_lower.startswith("gpt")
            or model_lower.startswith("openai")
            or (_OPENAI_REASONING_MODEL.search(model_lower) is not None)
        ):
            return "OPENAI_API_KEY"
        elif model_lower.startswith("claude") or model_lower.startswith("anthropic"):
            return "ANTHROPIC_API_KEY"
        elif model_lower.startswith("groq"):
            return "GROQ_API_KEY"
        elif model_lower.startswith("grok") or model_lower.startswith("xai"):
            return "XAI_API_KEY"
        elif model_lower.startswith("mistral"):
            return "MISTRAL_API_KEY"
        elif model_lower.startswith("cohere") or model_lower.startswith("command"):
            return "COHERE_API_KEY"
        elif model_lower.startswith("deepseek"):
            return "DEEPSEEK_API_KEY"

        return None

    def get_api_key_for_model(self, model: str) -> str | None:
        """Get the appropriate API key value for a given model."""
        var_name = self.get_api_key_name_for_model(model)
        if var_name:
            return os.environ.get(var_name)
        return None


# Global config instance
config = Config()
