"""Pydantic v2 schemas and data structures for database entities."""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class GuildModuleFlag(enum.IntFlag):
    """Bitmask representation for high-speed module enablement checks."""

    NONE = 0
    MODERATION = 1 << 0
    FUN = 1 << 1
    GENERAL = 1 << 2
    ALL = MODERATION | FUN | GENERAL

    @classmethod
    def from_name(cls, name: str) -> GuildModuleFlag:
        """Resolve a module string name to its corresponding IntFlag."""
        try:
            return cls[name.upper()]
        except KeyError:
            return cls.NONE


class GuildSettings(BaseModel):
    """Configuration settings for a Discord guild."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    guild_id: int
    prefix: str = "!"
    modlog_channel_id: int | None = None
    welcome_channel_id: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GuildModule(BaseModel):
    """Module toggle state for a Discord guild."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    guild_id: int
    module: str
    enabled: bool = True


class GuildRole(BaseModel):
    """Configured administrative or moderation role for a Discord guild."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    guild_id: int
    role_id: int
    role_type: str


class BlacklistEntry(BaseModel):
    """Global user blacklist entry."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    user_id: int
    reason: str = "No reason specified"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: int | None = None


class ModCase(BaseModel):
    """Case-tracked moderation action."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int | None = None
    guild_id: int
    case_number: int
    action: str
    user_id: int
    moderator_id: int
    reason: str = "Not specified"
    message_id: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WarningReason(BaseModel):
    """Configured warning reason template with point weight."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    guild_id: int
    name: str
    points: int = 1
    description: str | None = None


class WarningAction(BaseModel):
    """Configured escalation rule threshold for accumulated warning points."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    guild_id: int
    points: int
    action: str
    duration_seconds: int | None = None


class WarningSettings(BaseModel):
    """Guild settings for warning points decay and policy."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    guild_id: int
    decay_days: int = 30


class WarningRecord(BaseModel):
    """Individual infraction warning assigned to a guild member."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int | None = None
    guild_id: int
    user_id: int
    moderator_id: int
    reason: str
    points: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    case_number: int | None = None

    @property
    def is_expired(self) -> bool:
        """Determine whether the warning points have decayed."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) >= self.expires_at


class ReminderRecord(BaseModel):
    """Scheduled user or recurring broadcast reminder."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int | None = None
    user_id: int
    guild_id: int | None = None
    channel_id: int | None = None
    message: str
    remind_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    repeat_interval_seconds: int | None = None
