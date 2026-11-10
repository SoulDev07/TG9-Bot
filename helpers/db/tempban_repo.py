"""Repository handling temporary ban schedules and expirations."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from helpers.db.base import BaseRepository

if TYPE_CHECKING:
    from helpers.db.database import DatabaseManager


class TempBanRepository(BaseRepository):
    """Repository handling temporary ban schedules with automated unban workers."""

    __slots__ = ()

    def __init__(self, db: DatabaseManager) -> None:
        super().__init__(db)

    async def add_tempban(
        self,
        guild_id: int,
        user_id: int,
        unban_at: datetime,
        reason: str = "Temporary ban expired",
    ) -> None:
        """Schedule or update a temporary ban expiration timestamp."""
        unban_iso = unban_at.isoformat()
        async with self.db.write() as conn:
            await conn.execute(
                """
                INSERT INTO temp_bans (guild_id, user_id, unban_at, reason)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    unban_at = excluded.unban_at,
                    reason = excluded.reason
                """,
                (guild_id, user_id, unban_iso, reason),
            )
            await conn.commit()

    async def remove_tempban(self, guild_id: int, user_id: int) -> bool:
        """Remove a temporary ban record upon manual or automated unban."""
        async with self.db.write() as conn:
            cursor = await conn.execute(
                """
                DELETE FROM temp_bans
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def get_tempban(self, guild_id: int, user_id: int) -> datetime | None:
        """Fetch the expiration timestamp for an active temporary ban."""
        async with self.db.read() as conn:
            cursor = await conn.execute(
                """
                SELECT unban_at FROM temp_bans
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return datetime.fromisoformat(row["unban_at"])

    async def get_expired_tempbans(self, now: datetime) -> list[tuple[int, int, str]]:
        """Fetch all temporary bans whose expiration timestamp has passed."""
        now_iso = now.isoformat()
        async with self.db.read() as conn:
            cursor = await conn.execute(
                """
                SELECT guild_id, user_id, reason
                FROM temp_bans
                WHERE unban_at <= ?
                ORDER BY unban_at ASC
                """,
                (now_iso,),
            )
            rows = await cursor.fetchall()
            return [(row["guild_id"], row["user_id"], row["reason"]) for row in rows]
