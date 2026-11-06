"""Repository handling per-guild settings, modules, and roles with in-memory caching."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from helpers.db.base import BaseRepository
from helpers.db.models import GuildSettings

if TYPE_CHECKING:
    import discord

    from helpers.db.database import DatabaseManager


class GuildRepository(BaseRepository):
    """Repository handling per-guild settings, modules, and roles with in-memory caching."""

    def __init__(self, db: "DatabaseManager") -> None:
        super().__init__(db)
        self._prefix_cache: dict[int, str] = {}
        self._module_cache: dict[tuple[int, str], bool] = {}
        self._role_cache: dict[tuple[int, str], set[int]] = {}

    async def get_prefix(self, guild_id: int, default: str = "!") -> str:
        """Fetch custom prefix from memory cache or database."""
        if guild_id in self._prefix_cache:
            return self._prefix_cache[guild_id]

        settings = await self.get(guild_id)
        prefix = settings.prefix if settings else default
        self._prefix_cache[guild_id] = prefix
        return prefix

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
            settings = GuildSettings(
                guild_id=row["guild_id"],
                prefix=row["prefix"],
                modlog_channel_id=row["modlog_channel_id"],
                welcome_channel_id=row["welcome_channel_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            self._prefix_cache[guild_id] = settings.prefix
            return settings

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

        self._prefix_cache[guild_id] = default_prefix
        for module in ("moderation", "fun", "general"):
            self._module_cache[(guild_id, module)] = True

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
        self._prefix_cache[guild_id] = prefix

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
        cache_key = (guild_id, module.lower())
        if cache_key in self._module_cache:
            return self._module_cache[cache_key]

        async with await self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT enabled FROM guild_modules WHERE guild_id = ? AND module = ?",
                (guild_id, module.lower()),
            )
            row = await cursor.fetchone()
            enabled = bool(row["enabled"]) if row is not None else True
            self._module_cache[cache_key] = enabled
            return enabled

    async def set_module_enabled(self, guild_id: int, module: str, enabled: bool) -> None:
        """Toggle an individual module on or off for a guild."""
        normalized_module = module.lower()
        async with await self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO guild_modules (guild_id, module, enabled)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, module) DO UPDATE SET enabled = excluded.enabled
                """,
                (guild_id, normalized_module, int(enabled)),
            )
            await conn.commit()
        self._module_cache[(guild_id, normalized_module)] = enabled

    async def add_role(self, guild_id: int, role_id: int, role_type: str) -> None:
        """Assign an administrative or moderator role to a guild."""
        normalized_type = role_type.lower()
        await self.get_or_create(guild_id)

        async with await self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT OR IGNORE INTO guild_roles (guild_id, role_id, role_type)
                VALUES (?, ?, ?)
                """,
                (guild_id, role_id, normalized_type),
            )
            await conn.commit()

        if (guild_id, normalized_type) in self._role_cache:
            self._role_cache[(guild_id, normalized_type)].add(role_id)
        else:
            self._role_cache[(guild_id, normalized_type)] = {role_id}

    async def remove_role(self, guild_id: int, role_id: int, role_type: str) -> bool:
        """Remove a configured administrative or moderator role."""
        normalized_type = role_type.lower()
        async with await self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                DELETE FROM guild_roles
                WHERE guild_id = ? AND role_id = ? AND role_type = ?
                """,
                (guild_id, role_id, normalized_type),
            )
            await conn.commit()
            removed = cursor.rowcount > 0

        if removed and (guild_id, normalized_type) in self._role_cache:
            self._role_cache[(guild_id, normalized_type)].discard(role_id)
        return removed

    async def get_roles(self, guild_id: int, role_type: str) -> set[int]:
        """Fetch all configured role IDs for a role type in a guild."""
        normalized_type = role_type.lower()
        cache_key = (guild_id, normalized_type)
        if cache_key in self._role_cache:
            return set(self._role_cache[cache_key])

        async with await self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT role_id FROM guild_roles WHERE guild_id = ? AND role_type = ?",
                (guild_id, normalized_type),
            )
            rows = await cursor.fetchall()
            role_ids = {row["role_id"] for row in rows}
            self._role_cache[cache_key] = role_ids
            return set(role_ids)

    async def has_role_type(self, member: "discord.Member", role_type: str) -> bool:
        """Check if a guild member has any configured role matching the role type."""
        configured_roles = await self.get_roles(member.guild.id, role_type)
        if not configured_roles:
            return False
        return any(role.id in configured_roles for role in member.roles)

    async def get_all_roles(self, guild_id: int) -> dict[str, set[int]]:
        """Fetch all configured roles grouped by type for a guild."""
        async with await self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT role_id, role_type FROM guild_roles WHERE guild_id = ?",
                (guild_id,),
            )
            rows = await cursor.fetchall()
            result: dict[str, set[int]] = {"admin": set(), "mod": set()}
            for row in rows:
                rtype = row["role_type"].lower()
                result.setdefault(rtype, set()).add(row["role_id"])
                self._role_cache.setdefault((guild_id, rtype), set()).add(row["role_id"])
            return result
