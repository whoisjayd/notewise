"""Configuration management for yt-study."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Global configuration for the application."""
    
    # LLM Configuration
    default_model: str = "gemini/gemini-2.0-flash"
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    xai_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None
    
    # Chunking Configuration  
    chunk_size: int = 4000  # tokens
    chunk_overlap: int = 200  # tokens
    
    # Concurrency Configuration
    max_concurrent_videos: int = 1
    
    # Output Configuration
    default_output_dir: Path = Path("./output")
    
    # Transcript Configuration
    default_languages: List[str] = field(default_factory=lambda: ["en"])

    # Security: Allowed keys for environment injection
    ALLOWED_KEYS = {
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GROQ_API_KEY",
        "XAI_API_KEY",
        "MISTRAL_API_KEY",
        "DEFAULT_MODEL",
        "OUTPUT_DIR",
        "MAX_CONCURRENT_VIDEOS",
    }
    
    def __post_init__(self):
        """Load configuration from user config file and environment variables."""
        # First, try to load from user config file
        self._load_from_user_config()
        
        # Then load/override with environment variables
        self.gemini_api_key = os.getenv("GEMINI_API_KEY") or self.gemini_api_key
        self.openai_api_key = os.getenv("OPENAI_API_KEY") or self.openai_api_key
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY") or self.anthropic_api_key
        self.groq_api_key = os.getenv("GROQ_API_KEY") or self.groq_api_key
        self.xai_api_key = os.getenv("XAI_API_KEY") or self.xai_api_key
        self.mistral_api_key = os.getenv("MISTRAL_API_KEY") or self.mistral_api_key
        
        # Load default model and output dir from config
        env_model = os.getenv("DEFAULT_MODEL")
        if env_model:
            self.default_model = env_model
            
        env_output = os.getenv("OUTPUT_DIR")
        if env_output:
            self.default_output_dir = Path(env_output)
    
    def _load_from_user_config(self):
        """Load configuration from user's config file."""
        config_path = Path.home() / ".yt-study" / "config.env"
        
        if not config_path.exists():
            return
        
        try:
            with open(config_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        if key in self.ALLOWED_KEYS:
                            # Set in environment for other libraries
                            if key not in os.environ:
                                os.environ[key] = value
                        else:
                            logger.warning(f"Ignoring unauthorized config key: {key}")
                            
        except Exception:
            pass  # Silently fail if config file is corrupted
    
    def get_api_key_for_model(self, model: str) -> Optional[str]:
        """Get the appropriate API key for a given model."""
        model_lower = model.lower()
        
        if "gemini" in model_lower or "vertex" in model_lower:
            return self.gemini_api_key
        elif "gpt" in model_lower or "openai" in model_lower:
            return self.openai_api_key
        elif "claude" in model_lower or "anthropic" in model_lower:
            return self.anthropic_api_key
        elif "groq" in model_lower:
            return self.groq_api_key
        elif "grok" in model_lower or "xai" in model_lower:
            return self.xai_api_key
        elif "mistral" in model_lower:
            return self.mistral_api_key
        
        return None


# Global config instance
config = Config()
