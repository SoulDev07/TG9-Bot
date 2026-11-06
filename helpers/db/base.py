"""Abstract base repository providing shared database access semantics."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from helpers.db.database import DatabaseManager


class BaseRepository:
    """Base repository encapsulating DatabaseManager reference."""

    def __init__(self, db: "DatabaseManager") -> None:
        self.db = db
