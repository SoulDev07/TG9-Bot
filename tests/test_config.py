"""Unit tests for configuration loading and validation."""

from __future__ import annotations

from helpers.config import BotConfig


def test_bot_config_defaults() -> None:
    """Verify default values and helper methods for BotConfig."""
    config = BotConfig(
        bot_prefix="!test",
        owners={123456789, 987654321},
    )
    assert config.bot_prefix == "!test"
    assert config.is_owner(123456789) is True
    assert config.is_owner(987654321) is True
    assert config.is_owner(111111111) is False
    assert config.database_path == "data/tg9.db"
    assert config.log_level == "INFO"
