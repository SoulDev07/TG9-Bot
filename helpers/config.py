"""Typed application configuration models using Pydantic Settings."""

import json
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_FILE_PATH = Path("config.json")


def _read_config_json() -> dict[str, Any]:
    """Read static fallback defaults from config.json if present."""
    if CONFIG_FILE_PATH.is_file():
        try:
            with open(CONFIG_FILE_PATH, encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            return {}
    return {}


class BotConfig(BaseSettings):
    """Validated bot configuration merging .env, environment variables, and config.json."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    token: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="TOKEN",
        description="Discord bot application token",
    )
    bot_prefix: str = "Tg9 "
    bot_invite_link: str = ""
    owners: set[int] = Field(default_factory=set)
    test_guild: int | None = None
    guild_id: int | None = None
    statuses: list[str] = Field(default_factory=list)
    log_level: str = "INFO"
    json_logs: bool = False
    sentry_dsn: str | None = None

    def is_owner(self, user_id: int) -> bool:
        """Check if a given user ID is an authorized bot owner."""
        return user_id in self.owners

    def __getitem__(self, item: str) -> Any:
        """Allow subscript access for backwards compatibility."""
        try:
            return getattr(self, item)
        except AttributeError as err:
            raise KeyError(item) from err

    def get(self, item: str, default: Any = None) -> Any:
        """Allow dict-like get method for backwards compatibility."""
        return getattr(self, item, default)


_config_instance: BotConfig | None = None


def load_config() -> BotConfig:
    """Load, validate, and cache the bot configuration."""
    global _config_instance
    json_defaults = _read_config_json()

    # Pre-populate owners if provided as a list in config.json
    raw_owners = json_defaults.get("owners", [])
    if isinstance(raw_owners, list):
        json_defaults["owners"] = set(raw_owners)

    _config_instance = BotConfig(**json_defaults)
    return _config_instance


def get_config() -> BotConfig:
    """Retrieve the cached configuration instance, loading if necessary."""
    global _config_instance
    if _config_instance is None:
        return load_config()
    return _config_instance
