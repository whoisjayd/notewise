"""Configuration management for yt-study."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path


logger = logging.getLogger(__name__)


@dataclass
class Config:
    """
    Global configuration for the application.

    Manages loading settings from environment variables and config files.
    """

    # LLM Configuration
    default_model: str = "gemini/gemini-2.0-flash"
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

        env_concurrency = os.getenv("MAX_CONCURRENT_VIDEOS")
        if env_concurrency:
            try:
                self.max_concurrent_videos = int(env_concurrency)
            except ValueError:
                logger.warning(
                    f"Invalid MAX_CONCURRENT_VIDEOS value: {env_concurrency}. "
                    f"Using default {self.max_concurrent_videos}"
                )

        env_youtube_rpm = os.getenv("YOUTUBE_REQUESTS_PER_MINUTE")
        if env_youtube_rpm:
            try:
                youtube_rpm_value = int(env_youtube_rpm)
                if youtube_rpm_value < 1:
                    logger.warning(
                        "YOUTUBE_REQUESTS_PER_MINUTE must be >= 1: "
                        f"{env_youtube_rpm}. Using default "
                        f"{self.youtube_requests_per_minute}"
                    )
                else:
                    self.youtube_requests_per_minute = youtube_rpm_value
            except ValueError:
                logger.warning(
                    "Invalid YOUTUBE_REQUESTS_PER_MINUTE value: "
                    f"{env_youtube_rpm}. Using default "
                    f"{self.youtube_requests_per_minute}"
                )

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
        model_lower = model.lower()

        if "gemini" in model_lower or "vertex" in model_lower:
            return "GEMINI_API_KEY"
        elif "gpt" in model_lower or "openai" in model_lower:
            return "OPENAI_API_KEY"
        elif "claude" in model_lower or "anthropic" in model_lower:
            return "ANTHROPIC_API_KEY"
        elif "groq" in model_lower:
            return "GROQ_API_KEY"
        elif "grok" in model_lower or "xai" in model_lower:
            return "XAI_API_KEY"
        elif "mistral" in model_lower:
            return "MISTRAL_API_KEY"
        elif "cohere" in model_lower or "command" in model_lower:
            return "COHERE_API_KEY"
        elif "deepseek" in model_lower:
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
