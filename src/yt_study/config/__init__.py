"""Application configuration for yt-study."""

from .settings import AppSettings, get_cache_db_path, get_state_dir, settings


# Backward-compat alias used throughout existing code
config = settings

__all__ = ["AppSettings", "settings", "config", "get_state_dir", "get_cache_db_path"]
