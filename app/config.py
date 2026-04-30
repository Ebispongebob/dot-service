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

    # Lark / Feishu polling notification bridge (方案 A)
    lark_notify_enabled: bool = False
    lark_notify_cli: str = "lark-cli"
    lark_notify_cli_timeout_seconds: int = 20
    lark_notify_identity: str = "user"
    lark_notify_profile: str = ""
    lark_notify_chat_ids: str = ""
    lark_notify_user_ids: str = ""
    lark_notify_keywords: str = ""
    lark_notify_mention_ids: str = ""
    lark_notify_monitor_all: bool = False
    lark_notify_poll_interval_seconds: int = 60
    lark_notify_lookback_minutes: int = 10
    lark_notify_page_size: int = 20
    lark_notify_skip_existing_on_start: bool = True
    lark_notify_state_file: str = ".runtime/lark_notify_state.json"
    lark_notify_max_seen_messages: int = 1000
    lark_notify_max_messages_per_push: int = 3
    lark_notify_max_message_chars: int = 48
    lark_notify_dot_title: str = "飞书通知"
    lark_notify_dot_signature: str = "Lark Bridge"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
