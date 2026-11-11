"""Typed application configuration models using Pydantic Settings."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class BotConfig(BaseSettings):
    """Validated bot configuration loaded from environment variables, .env, and config.json."""

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
    database_path: str = "data/tg9.db"
    log_level: str = "INFO"
    json_logs: bool = False
    sentry_dsn: str | None = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Layer configuration: init args > env vars > .env > config.json."""
        config_path = Path("config.json")
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings, dotenv_settings]
        if config_path.exists():
            sources.append(JsonConfigSettingsSource(settings_cls, json_file=config_path))
        sources.append(file_secret_settings)
        return tuple(sources)

    def is_owner(self, user_id: int) -> bool:
        """Check if a given user ID is an authorized bot owner."""
        return user_id in self.owners


_config_instance: BotConfig | None = None


def load_config() -> BotConfig:
    """Load, validate, and cache the bot configuration."""
    global _config_instance
    _config_instance = BotConfig()
    return _config_instance


def get_config() -> BotConfig:
    """Retrieve the cached configuration instance, loading if necessary."""
    global _config_instance
    if _config_instance is None:
        return load_config()
    return _config_instance
