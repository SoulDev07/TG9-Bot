"""Repository handling per-guild settings, modules, and roles using aiocache."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from aiocache import SimpleMemoryCache

from core.db.base import BaseRepository
from core.db.models import GuildModuleFlag, GuildSettings

if TYPE_CHECKING:
    import discord

    from core.db.database import DatabaseManager


class GuildRepository(BaseRepository):
    """Repository handling per-guild settings, modules, and roles with aiocache."""

    __slots__ = ("_cache",)

    def __init__(self, db: DatabaseManager) -> None:
        super().__init__(db)
        self._cache = SimpleMemoryCache(ttl=300)

    async def get_prefix(self, guild_id: int, default: str = "!") -> str:
        """Fetch custom prefix from memory cache or database."""
        cache_key = f"prefix:{guild_id}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        settings = await self.get(guild_id)
        prefix = settings.prefix if settings else default
        await self._cache.set(cache_key, prefix, ttl=600)
        return prefix

    async def get(self, guild_id: int) -> GuildSettings | None:
        """Fetch settings for a guild, or return None if unconfigured."""
        cache_key = f"guild_settings:{guild_id}"
        cached: GuildSettings | None = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        async with self.db.read() as conn:
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
            await self._cache.set(cache_key, settings, ttl=300)
            await self._cache.set(f"prefix:{guild_id}", settings.prefix, ttl=600)
            return settings

    async def get_or_create(self, guild_id: int, default_prefix: str = "!") -> GuildSettings:
        """Fetch guild settings, or provision default records if first time seen."""
        existing = await self.get(guild_id)
        if existing:
            return existing

        now = datetime.now(UTC)
        now_iso = now.isoformat()
        async with self.db.write() as conn:
            await conn.execute(
                """
                INSERT OR IGNORE INTO guild_settings
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

        settings = await self.get(guild_id)
        if settings is not None:
            return settings

        new_settings = GuildSettings(
            guild_id=guild_id,
            prefix=default_prefix,
            modlog_channel_id=None,
            welcome_channel_id=None,
            created_at=now,
            updated_at=now,
        )
        await self._cache.set(f"guild_settings:{guild_id}", new_settings, ttl=300)
        await self._cache.set(f"prefix:{guild_id}", default_prefix, ttl=600)
        for module in ("moderation", "fun", "general"):
            await self._cache.set(f"mod:{guild_id}:{module}", True, ttl=300)

        return new_settings

    async def update_prefix(self, guild_id: int, prefix: str) -> None:
        """Update the custom prefix for a guild."""
        now_iso = datetime.now(UTC).isoformat()
        async with self.db.write() as conn:
            await conn.execute(
                """
                UPDATE guild_settings
                SET prefix = ?, updated_at = ?
                WHERE guild_id = ?
                """,
                (prefix, now_iso, guild_id),
            )
            await conn.commit()
        await self._cache.delete(f"guild_settings:{guild_id}")
        await self._cache.set(f"prefix:{guild_id}", prefix, ttl=600)

    async def set_modlog_channel(self, guild_id: int, channel_id: int | None) -> None:
        """Set or clear the designated moderation audit log channel."""
        now_iso = datetime.now(UTC).isoformat()
        async with self.db.write() as conn:
            await conn.execute(
                """
                UPDATE guild_settings
                SET modlog_channel_id = ?, updated_at = ?
                WHERE guild_id = ?
                """,
                (channel_id, now_iso, guild_id),
            )
            await conn.commit()
        await self._cache.delete(f"guild_settings:{guild_id}")

    async def set_welcome_channel(self, guild_id: int, channel_id: int | None) -> None:
        """Set or clear the welcome announcements channel."""
        now_iso = datetime.now(UTC).isoformat()
        async with self.db.write() as conn:
            await conn.execute(
                """
                UPDATE guild_settings
                SET welcome_channel_id = ?, updated_at = ?
                WHERE guild_id = ?
                """,
                (channel_id, now_iso, guild_id),
            )
            await conn.commit()
        await self._cache.delete(f"guild_settings:{guild_id}")

    async def is_module_enabled(self, guild_id: int, module: str) -> bool:
        """Check whether a specific feature module is enabled in a guild."""
        cache_key = f"mod:{guild_id}:{module.lower()}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        async with self.db.read() as conn:
            cursor = await conn.execute(
                "SELECT enabled FROM guild_modules WHERE guild_id = ? AND module = ?",
                (guild_id, module.lower()),
            )
            row = await cursor.fetchone()
            enabled = bool(row["enabled"]) if row is not None else True
            await self._cache.set(cache_key, enabled, ttl=300)
            return enabled

    async def get_module_flags(self, guild_id: int) -> GuildModuleFlag:
        """Fetch all enabled modules for a guild as a consolidated bitmask."""
        flags = GuildModuleFlag.NONE
        async with self.db.read() as conn:
            cursor = await conn.execute(
                "SELECT module, enabled FROM guild_modules WHERE guild_id = ?",
                (guild_id,),
            )
            rows = await cursor.fetchall()
            for row in rows:
                if row["enabled"]:
                    flags |= GuildModuleFlag.from_name(row["module"])
        return flags

    async def set_module_enabled(self, guild_id: int, module: str, enabled: bool) -> None:
        """Toggle an individual module on or off for a guild."""
        normalized_module = module.lower()
        async with self.db.write() as conn:
            await conn.execute(
                """
                INSERT INTO guild_modules (guild_id, module, enabled)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, module) DO UPDATE SET enabled = excluded.enabled
                """,
                (guild_id, normalized_module, int(enabled)),
            )
            await conn.commit()
        await self._cache.set(f"mod:{guild_id}:{normalized_module}", enabled, ttl=300)

    async def add_role(self, guild_id: int, role_id: int, role_type: str) -> None:
        """Assign an administrative or moderator role to a guild."""
        normalized_type = role_type.lower()
        await self.get_or_create(guild_id)

        async with self.db.write() as conn:
            await conn.execute(
                """
                INSERT OR IGNORE INTO guild_roles (guild_id, role_id, role_type)
                VALUES (?, ?, ?)
                """,
                (guild_id, role_id, normalized_type),
            )
            await conn.commit()

        await self._cache.delete(f"roles:{guild_id}:{normalized_type}")

    async def remove_role(self, guild_id: int, role_id: int, role_type: str) -> bool:
        """Remove a configured administrative or moderator role."""
        normalized_type = role_type.lower()
        async with self.db.write() as conn:
            cursor = await conn.execute(
                """
                DELETE FROM guild_roles
                WHERE guild_id = ? AND role_id = ? AND role_type = ?
                """,
                (guild_id, role_id, normalized_type),
            )
            await conn.commit()
            removed = cursor.rowcount > 0

        if removed:
            await self._cache.delete(f"roles:{guild_id}:{normalized_type}")
        return removed

    async def get_roles(self, guild_id: int, role_type: str) -> set[int]:
        """Fetch all configured role IDs for a role type in a guild."""
        normalized_type = role_type.lower()
        cache_key = f"roles:{guild_id}:{normalized_type}"
        cached_roles = await self._cache.get(cache_key)
        if cached_roles is not None:
            return set(cached_roles)

        async with self.db.read() as conn:
            cursor = await conn.execute(
                "SELECT role_id FROM guild_roles WHERE guild_id = ? AND role_type = ?",
                (guild_id, normalized_type),
            )
            rows = await cursor.fetchall()
            role_ids = {row["role_id"] for row in rows}
            await self._cache.set(cache_key, role_ids, ttl=300)
            return set(role_ids)

    async def has_role_type(self, member: discord.Member, role_type: str) -> bool:
        """Check if a guild member has any configured role matching the role type."""
        configured_roles = await self.get_roles(member.guild.id, role_type)
        if not configured_roles:
            return False
        return any(role.id in configured_roles for role in member.roles)

    async def get_all_roles(self, guild_id: int) -> dict[str, set[int]]:
        """Fetch all configured roles grouped by type for a guild."""
        async with self.db.read() as conn:
            cursor = await conn.execute(
                "SELECT role_id, role_type FROM guild_roles WHERE guild_id = ?",
                (guild_id,),
            )
            rows = await cursor.fetchall()
            result: dict[str, set[int]] = {"admin": set(), "mod": set(), "selfrole": set()}
            for row in rows:
                rtype = row["role_type"].lower()
                result.setdefault(rtype, set()).add(row["role_id"])

            for rtype, rids in result.items():
                await self._cache.set(f"roles:{guild_id}:{rtype}", set(rids), ttl=300)
            return result
