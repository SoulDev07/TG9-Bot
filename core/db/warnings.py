"""Repository handling member warnings, point decay, and escalation rules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from aiocache import SimpleMemoryCache

from core.db.base import BaseRepository
from core.db.models import WarningAction, WarningReason, WarningRecord, WarningSettings

if TYPE_CHECKING:
    from core.db.database import DatabaseManager

DEFAULT_ACTIONS: list[tuple[int, str, int | None]] = [
    (3, "timeout", 3600),
    (5, "kick", None),
    (10, "ban", None),
]

DEFAULT_REASONS: list[tuple[str, int, str]] = [
    ("spam", 1, "Unsolicited repetitive messages or advertising"),
    ("toxicity", 2, "Harassment, incivility, or offensive behavior"),
    ("hate speech", 5, "Severe hate speech, slurs, or discrimination"),
]


class WarningRepository(BaseRepository):
    """Repository managing warnings, point values, decay intervals, and escalation actions."""

    __slots__ = ("_cache",)

    def __init__(self, db: DatabaseManager) -> None:
        super().__init__(db)
        self._cache = SimpleMemoryCache()

    async def get_settings(self, guild_id: int) -> WarningSettings:
        """Fetch warning settings for a guild or return default configuration."""
        cache_key = f"warn_settings:{guild_id}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        async with self.db.read() as conn:
            cursor = await conn.execute(
                """
                SELECT guild_id, decay_days
                FROM warning_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
            )
            row = await cursor.fetchone()
            if row:
                settings = WarningSettings(
                    guild_id=row["guild_id"],
                    decay_days=row["decay_days"],
                )
            else:
                settings = WarningSettings(guild_id=guild_id, decay_days=30)

        await self._cache.set(cache_key, settings, ttl=300)
        return settings

    async def set_decay(self, guild_id: int, decay_days: int) -> None:
        """Configure warning points decay days for a guild (0 disables decay)."""
        async with self.db.write() as conn:
            await conn.execute(
                """
                INSERT INTO warning_settings (guild_id, decay_days)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    decay_days = excluded.decay_days
                """,
                (guild_id, max(0, decay_days)),
            )
            await conn.commit()

        await self._cache.delete(f"warn_settings:{guild_id}")

    async def get_actions(self, guild_id: int) -> list[WarningAction]:
        """Fetch configured escalation actions ordered by point threshold ascending."""
        cache_key = f"warn_actions:{guild_id}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        async with self.db.read() as conn:
            cursor = await conn.execute(
                """
                SELECT points, action, duration_seconds
                FROM warning_actions
                WHERE guild_id = ?
                ORDER BY points ASC
                """,
                (guild_id,),
            )
            rows = await cursor.fetchall()

        if rows:
            actions = [
                WarningAction(
                    guild_id=guild_id,
                    points=row["points"],
                    action=row["action"],
                    duration_seconds=row["duration_seconds"],
                )
                for row in rows
            ]
        else:
            actions = [
                WarningAction(
                    guild_id=guild_id,
                    points=pts,
                    action=act,
                    duration_seconds=dur,
                )
                for pts, act, dur in DEFAULT_ACTIONS
            ]

        await self._cache.set(cache_key, actions, ttl=300)
        return actions

    async def set_action(
        self,
        guild_id: int,
        points: int,
        action: str,
        duration_seconds: int | None = None,
    ) -> None:
        """Register or update an escalation rule threshold."""
        async with self.db.write() as conn:
            await conn.execute(
                """
                INSERT INTO warning_actions (guild_id, points, action, duration_seconds)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, points) DO UPDATE SET
                    action = excluded.action,
                    duration_seconds = excluded.duration_seconds
                """,
                (guild_id, points, action.lower(), duration_seconds),
            )
            await conn.commit()

        await self._cache.delete(f"warn_actions:{guild_id}")

    async def delete_action(self, guild_id: int, points: int) -> bool:
        """Remove an escalation rule threshold."""
        async with self.db.write() as conn:
            cursor = await conn.execute(
                """
                DELETE FROM warning_actions
                WHERE guild_id = ? AND points = ?
                """,
                (guild_id, points),
            )
            await conn.commit()
            removed = cursor.rowcount > 0

        await self._cache.delete(f"warn_actions:{guild_id}")
        return removed

    async def get_reasons(self, guild_id: int) -> list[WarningReason]:
        """Fetch configured warning reasons with point weights."""
        cache_key = f"warn_reasons:{guild_id}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        async with self.db.read() as conn:
            cursor = await conn.execute(
                """
                SELECT name, points, description
                FROM warning_reasons
                WHERE guild_id = ?
                ORDER BY points ASC, name ASC
                """,
                (guild_id,),
            )
            rows = await cursor.fetchall()

        if rows:
            reasons = [
                WarningReason(
                    guild_id=guild_id,
                    name=row["name"],
                    points=row["points"],
                    description=row["description"],
                )
                for row in rows
            ]
        else:
            reasons = [
                WarningReason(
                    guild_id=guild_id,
                    name=name,
                    points=pts,
                    description=desc,
                )
                for name, pts, desc in DEFAULT_REASONS
            ]

        await self._cache.set(cache_key, reasons, ttl=300)
        return reasons

    async def get_reason(self, guild_id: int, name: str) -> WarningReason | None:
        """Find a warning reason by name for a guild."""
        reasons = await self.get_reasons(guild_id)
        name_clean = name.strip().lower()
        for r in reasons:
            if r.name.lower() == name_clean:
                return r
        return None

    async def set_reason(
        self,
        guild_id: int,
        name: str,
        points: int,
        description: str | None = None,
    ) -> None:
        """Register or update a preset warning reason with assigned point value."""
        async with self.db.write() as conn:
            await conn.execute(
                """
                INSERT INTO warning_reasons (guild_id, name, points, description)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, name) DO UPDATE SET
                    points = excluded.points,
                    description = excluded.description
                """,
                (guild_id, name.strip().lower(), max(1, points), description),
            )
            await conn.commit()

        await self._cache.delete(f"warn_reasons:{guild_id}")

    async def delete_reason(self, guild_id: int, name: str) -> bool:
        """Delete a configured warning reason preset."""
        async with self.db.write() as conn:
            cursor = await conn.execute(
                """
                DELETE FROM warning_reasons
                WHERE guild_id = ? AND LOWER(name) = LOWER(?)
                """,
                (guild_id, name.strip()),
            )
            await conn.commit()
            removed = cursor.rowcount > 0

        await self._cache.delete(f"warn_reasons:{guild_id}")
        return removed

    async def create_warning(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        reason: str,
        points: int = 1,
        expires_at: datetime | None = None,
        case_number: int | None = None,
    ) -> WarningRecord:
        """Record a new warning infraction assigned to a user."""
        now = datetime.now(UTC)
        now_iso = now.isoformat()
        expires_iso = expires_at.isoformat() if expires_at else None

        async with self.db.write() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO warnings (
                    guild_id, user_id, moderator_id, reason, points,
                    created_at, expires_at, case_number
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    user_id,
                    moderator_id,
                    reason,
                    points,
                    now_iso,
                    expires_iso,
                    case_number,
                ),
            )
            await conn.commit()
            warning_id = cursor.lastrowid

        return WarningRecord(
            id=warning_id,
            guild_id=guild_id,
            user_id=user_id,
            moderator_id=moderator_id,
            reason=reason,
            points=points,
            created_at=now,
            expires_at=expires_at,
            case_number=case_number,
        )

    async def get_active_points(
        self,
        guild_id: int,
        user_id: int,
        now: datetime | None = None,
    ) -> int:
        """Calculate the total non-decayed warning points accumulated by a member."""
        ref_time = (now or datetime.now(UTC)).isoformat()
        async with self.db.read() as conn:
            cursor = await conn.execute(
                """
                SELECT COALESCE(SUM(points), 0) AS total_points
                FROM warnings
                WHERE guild_id = ?
                  AND user_id = ?
                  AND (expires_at IS NULL OR expires_at > ?)
                """,
                (guild_id, user_id, ref_time),
            )
            row = await cursor.fetchone()
            return row["total_points"] if row else 0

    async def get_warnings(
        self,
        guild_id: int,
        user_id: int,
        active_only: bool = False,
        now: datetime | None = None,
    ) -> list[WarningRecord]:
        """Fetch warning records for a user ordered by newest first."""
        ref_time = (now or datetime.now(UTC)).isoformat()
        query = """
            SELECT id, guild_id, user_id, moderator_id, reason, points,
                   created_at, expires_at, case_number
            FROM warnings
            WHERE guild_id = ? AND user_id = ?
        """
        params: list[int | str] = [guild_id, user_id]

        if active_only:
            query += " AND (expires_at IS NULL OR expires_at > ?)"
            params.append(ref_time)

        query += " ORDER BY id DESC"

        async with self.db.read() as conn:
            cursor = await conn.execute(query, tuple(params))
            rows = await cursor.fetchall()

        records: list[WarningRecord] = []
        for row in rows:
            created_at = datetime.fromisoformat(row["created_at"])
            expires_at = datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None
            records.append(
                WarningRecord(
                    id=row["id"],
                    guild_id=row["guild_id"],
                    user_id=row["user_id"],
                    moderator_id=row["moderator_id"],
                    reason=row["reason"],
                    points=row["points"],
                    created_at=created_at,
                    expires_at=expires_at,
                    case_number=row["case_number"],
                )
            )

        return records

    async def delete_warning(self, guild_id: int, warning_id: int) -> bool:
        """Pardon or remove a specific warning record by its ID."""
        async with self.db.write() as conn:
            cursor = await conn.execute(
                """
                DELETE FROM warnings
                WHERE guild_id = ? AND id = ?
                """,
                (guild_id, warning_id),
            )
            await conn.commit()
            return cursor.rowcount > 0
