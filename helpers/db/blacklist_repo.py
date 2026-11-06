"""Repository handling global user blacklists with in-memory caching."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from helpers.db.base import BaseRepository
from helpers.db.models import BlacklistEntry
from helpers.logger import get_logger

if TYPE_CHECKING:
    from helpers.db.database import DatabaseManager

logger = get_logger()


class BlacklistRepository(BaseRepository):
    """Repository handling global user blacklists with in-memory caching."""

    def __init__(self, db: "DatabaseManager") -> None:
        super().__init__(db)
        self._cache: set[int] = set()
        self._cache_warmed = False

    async def warm_cache(self) -> None:
        """Pre-populate the in-memory blacklist cache on startup."""
        async with await self.db.get_connection() as conn:
            cursor = await conn.execute("SELECT user_id FROM blacklist")
            rows = await cursor.fetchall()
            self._cache = {row["user_id"] for row in rows}
            self._cache_warmed = True
        logger.info("blacklist_cache_warmed", count=len(self._cache))

    async def is_blacklisted(self, user_id: int) -> bool:
        """Check if a user is currently blacklisted from using the bot."""
        if self._cache_warmed:
            return user_id in self._cache

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

        self._cache.add(user_id)
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
            removed = cursor.rowcount > 0

        if removed:
            self._cache.discard(user_id)
        return removed

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
        if self._cache_warmed:
            return len(self._cache)

        async with await self.db.get_connection() as conn:
            cursor = await conn.execute("SELECT COUNT(*) AS count FROM blacklist")
            row = await cursor.fetchone()
            return row["count"] if row else 0
