"""Repository handling sequential moderation case records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from core.db.base import BaseRepository
from core.db.models import ModCase

if TYPE_CHECKING:
    from core.db.database import DatabaseManager


class ModCaseRepository(BaseRepository):
    """Repository handling sequential moderation case records."""

    __slots__ = ()

    def __init__(self, db: DatabaseManager) -> None:
        super().__init__(db)

    async def get_next_case_number(self, guild_id: int) -> int:
        """Calculate the next sequential case number for a given guild."""
        async with self.db.read() as conn:
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
        """Create a new sequentially numbered moderation case atomically."""
        now = datetime.now(UTC)
        now_iso = now.isoformat()
        action_clean = action.lower()

        async with self.db.write() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO mod_cases
                (guild_id, case_number, action, user_id, moderator_id,
                 reason, message_id, created_at)
                VALUES (
                    ?,
                    (SELECT COALESCE(MAX(case_number), 0) + 1 FROM mod_cases WHERE guild_id = ?),
                    ?, ?, ?, ?, ?, ?
                )
                RETURNING id, guild_id, case_number, action, user_id,
                          moderator_id, reason, message_id, created_at
                """,
                (
                    guild_id,
                    guild_id,
                    action_clean,
                    user_id,
                    moderator_id,
                    reason,
                    message_id,
                    now_iso,
                ),
            )
            row = await cursor.fetchone()
            await conn.commit()

        if row:
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

        return ModCase(
            guild_id=guild_id,
            case_number=1,
            action=action_clean,
            user_id=user_id,
            moderator_id=moderator_id,
            reason=reason,
            message_id=message_id,
            created_at=now,
        )

    async def get_case(self, guild_id: int, case_number: int) -> ModCase | None:
        """Fetch a specific moderation case by guild and case number."""
        async with self.db.read() as conn:
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

    async def get_cases_for_user(self, guild_id: int, user_id: int) -> list[ModCase]:
        """Fetch all moderation cases for a specific user ordered by case number descending."""
        async with self.db.read() as conn:
            cursor = await conn.execute(
                """
                SELECT id, guild_id, case_number, action, user_id,
                       moderator_id, reason, message_id, created_at
                FROM mod_cases
                WHERE guild_id = ? AND user_id = ?
                ORDER BY case_number DESC
                """,
                (guild_id, user_id),
            )
            rows = await cursor.fetchall()
            return [
                ModCase(
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
                for row in rows
            ]

    async def update_reason(self, guild_id: int, case_number: int, reason: str) -> bool:
        """Update the reason for an existing moderation case."""
        async with self.db.write() as conn:
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
        async with self.db.write() as conn:
            await conn.execute(
                """
                UPDATE mod_cases
                SET message_id = ?
                WHERE guild_id = ? AND case_number = ?
                """,
                (message_id, guild_id, case_number),
            )
            await conn.commit()
