"""Repository handling user reminders and recurring broadcast schedules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from core.db.base import BaseRepository
from core.db.models import ReminderRecord

if TYPE_CHECKING:
    import aiosqlite

    from core.db.database import DatabaseManager


class ReminderRepository(BaseRepository):
    """Repository handling scheduled reminders and recurring messages."""

    __slots__ = ()

    def __init__(self, db: DatabaseManager) -> None:
        super().__init__(db)

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> ReminderRecord:
        return ReminderRecord(
            id=row["id"],
            user_id=row["user_id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message=row["message"],
            remind_at=datetime.fromisoformat(row["remind_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            repeat_interval_seconds=row["repeat_interval_seconds"],
        )

    async def create_reminder(
        self,
        user_id: int,
        guild_id: int | None,
        channel_id: int | None,
        message: str,
        remind_at: datetime,
        repeat_interval_seconds: int | None = None,
    ) -> ReminderRecord:
        """Schedule a new user reminder or recurring broadcast."""
        created_at = datetime.now(UTC)
        async with self.db.write() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO reminders (
                    user_id, guild_id, channel_id, message, remind_at, created_at, repeat_interval_seconds
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    guild_id,
                    channel_id,
                    message,
                    remind_at.isoformat(),
                    created_at.isoformat(),
                    repeat_interval_seconds,
                ),
            )
            await conn.commit()
            reminder_id = cursor.lastrowid
            assert reminder_id is not None
            return ReminderRecord(
                id=reminder_id,
                user_id=user_id,
                guild_id=guild_id,
                channel_id=channel_id,
                message=message,
                remind_at=remind_at,
                created_at=created_at,
                repeat_interval_seconds=repeat_interval_seconds,
            )

    async def get_due_reminders(self, now: datetime) -> list[ReminderRecord]:
        """Fetch all reminders whose expiration timestamp has passed."""
        now_iso = now.isoformat()
        async with self.db.read() as conn:
            cursor = await conn.execute(
                """
                SELECT id, user_id, guild_id, channel_id, message, remind_at, created_at, repeat_interval_seconds
                FROM reminders
                WHERE remind_at <= ?
                ORDER BY remind_at ASC
                """,
                (now_iso,),
            )
            rows = await cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    async def get_user_reminders(self, user_id: int) -> list[ReminderRecord]:
        """Fetch all active reminders created by a specific user."""
        async with self.db.read() as conn:
            cursor = await conn.execute(
                """
                SELECT id, user_id, guild_id, channel_id, message, remind_at, created_at, repeat_interval_seconds
                FROM reminders
                WHERE user_id = ?
                ORDER BY remind_at ASC
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    async def get_reminder(self, reminder_id: int) -> ReminderRecord | None:
        """Fetch a specific reminder by ID."""
        async with self.db.read() as conn:
            cursor = await conn.execute(
                """
                SELECT id, user_id, guild_id, channel_id, message, remind_at, created_at, repeat_interval_seconds
                FROM reminders
                WHERE id = ?
                """,
                (reminder_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    async def update_remind_at(self, reminder_id: int, new_remind_at: datetime) -> bool:
        """Update remind_at timestamp for recurring schedules."""
        async with self.db.write() as conn:
            cursor = await conn.execute(
                """
                UPDATE reminders
                SET remind_at = ?
                WHERE id = ?
                """,
                (new_remind_at.isoformat(), reminder_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def delete_reminder(self, reminder_id: int, user_id: int | None = None) -> bool:
        """Delete a reminder by ID, optionally scoped to a user."""
        async with self.db.write() as conn:
            if user_id is not None:
                cursor = await conn.execute(
                    "DELETE FROM reminders WHERE id = ? AND user_id = ?",
                    (reminder_id, user_id),
                )
            else:
                cursor = await conn.execute(
                    "DELETE FROM reminders WHERE id = ?",
                    (reminder_id,),
                )
            await conn.commit()
            return cursor.rowcount > 0

    async def delete_reminders_batch(self, reminder_ids: list[int]) -> int:
        """Batch delete multiple reminders in a single query."""
        if not reminder_ids:
            return 0
        placeholders = ",".join("?" for _ in reminder_ids)
        async with self.db.write() as conn:
            cursor = await conn.execute(
                f"DELETE FROM reminders WHERE id IN ({placeholders})",
                tuple(reminder_ids),
            )
            await conn.commit()
            return cursor.rowcount
