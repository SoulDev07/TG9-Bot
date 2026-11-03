"""Pydantic v2 schemas for database entities."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class GuildSettings(BaseModel):
    """Configuration settings for a Discord guild."""

    guild_id: int
    prefix: str = "!"
    modlog_channel_id: int | None = None
    welcome_channel_id: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GuildModule(BaseModel):
    """Module toggle state for a Discord guild."""

    guild_id: int
    module: str
    enabled: bool = True


class GuildRole(BaseModel):
    """Configured administrative or moderation role for a Discord guild."""

    guild_id: int
    role_id: int
    role_type: str


class BlacklistEntry(BaseModel):
    """Global user blacklist entry."""

    user_id: int
    reason: str = "No reason specified"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: int | None = None


class ModCase(BaseModel):
    """Case-tracked moderation action."""

    id: int | None = None
    guild_id: int
    case_number: int
    action: str
    user_id: int
    moderator_id: int
    reason: str = "Not specified"
    message_id: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
