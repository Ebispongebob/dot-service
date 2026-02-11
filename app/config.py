"""
Configuration management for Dot Service.
Loads settings from environment variables / .env file.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Dot Cloud API
    dot_api_base_url: str = "https://dot.mindreset.tech"
    dot_api_key: str = ""

    # Default device (can be overridden per-request)
    dot_default_device_id: str = ""

    # Service
    service_host: str = "0.0.0.0"
    service_port: int = 8000

    # Quote/0 screen resolution
    screen_width: int = 296
    screen_height: int = 152

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
