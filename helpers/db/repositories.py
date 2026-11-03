"""Strongly-typed asynchronous repositories for database entities."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from helpers.db.models import BlacklistEntry, GuildSettings, ModCase

if TYPE_CHECKING:
    from helpers.db.database import DatabaseManager


class GuildRepository:
    """Repository handling per-guild settings, modules, and roles."""

    def __init__(self, db: "DatabaseManager") -> None:
        self.db = db

    async def get(self, guild_id: int) -> GuildSettings | None:
        """Fetch settings for a guild, or return None if unconfigured."""
        async with await self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM guild_settings WHERE guild_id = ?",
                (guild_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return GuildSettings(
                guild_id=row["guild_id"],
                prefix=row["prefix"],
                modlog_channel_id=row["modlog_channel_id"],
                welcome_channel_id=row["welcome_channel_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )

    async def get_or_create(self, guild_id: int, default_prefix: str = "!") -> GuildSettings:
        """Fetch guild settings, or provision default records if first time seen."""
        existing = await self.get(guild_id)
        if existing:
            return existing

        now = datetime.now(UTC)
        now_iso = now.isoformat()
        async with await self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings
                (guild_id, prefix, modlog_channel_id, welcome_channel_id, created_at, updated_at)
                VALUES (?, ?, NULL, NULL, ?, ?)
                """,
                (guild_id, default_prefix, now_iso, now_iso),
            )
            for module in ("moderation", "fun", "general"):
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO guild_modules (guild_id, module, enabled)
                    VALUES (?, ?, 1)
                    """,
                    (guild_id, module),
                )
            await conn.commit()

        return GuildSettings(
            guild_id=guild_id,
            prefix=default_prefix,
            modlog_channel_id=None,
            welcome_channel_id=None,
            created_at=now,
            updated_at=now,
        )

    async def update_prefix(self, guild_id: int, prefix: str) -> None:
        """Update the custom prefix for a guild."""
        now_iso = datetime.now(UTC).isoformat()
        async with await self.db.get_connection() as conn:
            await conn.execute(
                """
                UPDATE guild_settings
                SET prefix = ?, updated_at = ?
                WHERE guild_id = ?
                """,
                (prefix, now_iso, guild_id),
            )
            await conn.commit()

    async def set_modlog_channel(self, guild_id: int, channel_id: int | None) -> None:
        """Set or clear the designated moderation audit log channel."""
        now_iso = datetime.now(UTC).isoformat()
        async with await self.db.get_connection() as conn:
            await conn.execute(
                """
                UPDATE guild_settings
                SET modlog_channel_id = ?, updated_at = ?
                WHERE guild_id = ?
                """,
                (channel_id, now_iso, guild_id),
            )
            await conn.commit()

    async def set_welcome_channel(self, guild_id: int, channel_id: int | None) -> None:
        """Set or clear the welcome announcements channel."""
        now_iso = datetime.now(UTC).isoformat()
        async with await self.db.get_connection() as conn:
            await conn.execute(
                """
                UPDATE guild_settings
                SET welcome_channel_id = ?, updated_at = ?
                WHERE guild_id = ?
                """,
                (channel_id, now_iso, guild_id),
            )
            await conn.commit()

    async def is_module_enabled(self, guild_id: int, module: str) -> bool:
        """Check whether a specific feature module is enabled in a guild."""
        async with await self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT enabled FROM guild_modules WHERE guild_id = ? AND module = ?",
                (guild_id, module.lower()),
            )
            row = await cursor.fetchone()
            if row is None:
                return True
            return bool(row["enabled"])

    async def set_module_enabled(self, guild_id: int, module: str, enabled: bool) -> None:
        """Toggle an individual module on or off for a guild."""
        async with await self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO guild_modules (guild_id, module, enabled)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, module) DO UPDATE SET enabled = excluded.enabled
                """,
                (guild_id, module.lower(), int(enabled)),
            )
            await conn.commit()


class BlacklistRepository:
    """Repository handling global user blacklists."""

    def __init__(self, db: "DatabaseManager") -> None:
        self.db = db

    async def is_blacklisted(self, user_id: int) -> bool:
        """Check if a user is currently blacklisted from using the bot."""
        async with await self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT 1 FROM blacklist WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            return row is not None

    async def add(
        self,
        user_id: int,
        reason: str = "No reason specified",
        created_by: int | None = None,
    ) -> BlacklistEntry:
        """Add a user to the global blacklist."""
        now = datetime.now(UTC)
        now_iso = now.isoformat()
        async with await self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO blacklist (user_id, reason, created_at, created_by)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, reason, now_iso, created_by),
            )
            await conn.commit()

        return BlacklistEntry(
            user_id=user_id,
            reason=reason,
            created_at=now,
            created_by=created_by,
        )

    async def remove(self, user_id: int) -> bool:
        """Remove a user from the global blacklist. Returns True if deleted."""
        async with await self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM blacklist WHERE user_id = ?",
                (user_id,),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def get_all(self) -> list[BlacklistEntry]:
        """Fetch all blacklisted user records."""
        async with await self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT user_id, reason, created_at, created_by
                FROM blacklist
                ORDER BY created_at DESC
                """
            )
            rows = await cursor.fetchall()
            return [
                BlacklistEntry(
                    user_id=row["user_id"],
                    reason=row["reason"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    created_by=row["created_by"],
                )
                for row in rows
            ]

    async def count(self) -> int:
        """Count total blacklisted users."""
        async with await self.db.get_connection() as conn:
            cursor = await conn.execute("SELECT COUNT(*) AS count FROM blacklist")
            row = await cursor.fetchone()
            return row["count"] if row else 0


class ModCaseRepository:
    """Repository handling sequential moderation case records."""

    def __init__(self, db: "DatabaseManager") -> None:
        self.db = db

    async def get_next_case_number(self, guild_id: int) -> int:
        """Calculate the next sequential case number for a given guild."""
        async with await self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT COALESCE(MAX(case_number), 0) + 1 AS next_case
                FROM mod_cases
                WHERE guild_id = ?
                """,
                (guild_id,),
            )
            row = await cursor.fetchone()
            return row["next_case"] if row else 1

    async def create_case(
        self,
        guild_id: int,
        action: str,
        user_id: int,
        moderator_id: int,
        reason: str = "Not specified",
        message_id: int | None = None,
    ) -> ModCase:
        """Create a new sequentially numbered moderation case."""
        case_number = await self.get_next_case_number(guild_id)
        now = datetime.now(UTC)
        now_iso = now.isoformat()

        async with await self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO mod_cases
                (guild_id, case_number, action, user_id, moderator_id,
                 reason, message_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    case_number,
                    action.lower(),
                    user_id,
                    moderator_id,
                    reason,
                    message_id,
                    now_iso,
                ),
            )
            await conn.commit()
            case_id = cursor.lastrowid

        return ModCase(
            id=case_id,
            guild_id=guild_id,
            case_number=case_number,
            action=action.lower(),
            user_id=user_id,
            moderator_id=moderator_id,
            reason=reason,
            message_id=message_id,
            created_at=now,
        )

    async def get_case(self, guild_id: int, case_number: int) -> ModCase | None:
        """Fetch a specific moderation case by guild and case number."""
        async with await self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT id, guild_id, case_number, action, user_id,
                       moderator_id, reason, message_id, created_at
                FROM mod_cases
                WHERE guild_id = ? AND case_number = ?
                """,
                (guild_id, case_number),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return ModCase(
                id=row["id"],
                guild_id=row["guild_id"],
                case_number=row["case_number"],
                action=row["action"],
                user_id=row["user_id"],
                moderator_id=row["moderator_id"],
                reason=row["reason"],
                message_id=row["message_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )

    async def update_reason(self, guild_id: int, case_number: int, reason: str) -> bool:
        """Update the reason for an existing moderation case."""
        async with await self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE mod_cases
                SET reason = ?
                WHERE guild_id = ? AND case_number = ?
                """,
                (reason, guild_id, case_number),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def update_message_id(self, guild_id: int, case_number: int, message_id: int) -> None:
        """Record the Discord audit log message ID associated with a case embed."""
        async with await self.db.get_connection() as conn:
            await conn.execute(
                """
                UPDATE mod_cases
                SET message_id = ?
                WHERE guild_id = ? AND case_number = ?
                """,
                (message_id, guild_id, case_number),
            )
            await conn.commit()
