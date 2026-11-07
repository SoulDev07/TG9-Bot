"""Base repository providing shared database access semantics."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from helpers.db.database import DatabaseManager


class BaseRepository:
    """Base repository encapsulating DatabaseManager reference."""

    __slots__ = ("db",)

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
