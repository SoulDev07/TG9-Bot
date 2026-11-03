"""Asynchronous SQLite database manager using aiosqlite."""

from pathlib import Path

import aiosqlite

from helpers.logger import get_logger

logger = get_logger()

SCHEMA_DDL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    prefix TEXT NOT NULL DEFAULT '!',
    modlog_channel_id INTEGER,
    welcome_channel_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guild_modules (
    guild_id INTEGER NOT NULL,
    module TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (guild_id, module),
    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS guild_roles (
    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    role_type TEXT NOT NULL,
    PRIMARY KEY (guild_id, role_id, role_type),
    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS blacklist (
    user_id INTEGER PRIMARY KEY,
    reason TEXT NOT NULL DEFAULT 'No reason specified',
    created_at TEXT NOT NULL,
    created_by INTEGER
);

CREATE TABLE IF NOT EXISTS mod_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    case_number INTEGER NOT NULL,
    action TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT NOT NULL DEFAULT 'Not specified',
    message_id INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(guild_id, case_number)
);

CREATE INDEX IF NOT EXISTS idx_mod_cases_guild_user ON mod_cases(guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_guild_modules_guild ON guild_modules(guild_id);
"""


class DatabaseManager:
    """Manages SQLite connections and schema lifecycle via aiosqlite."""

    def __init__(self, db_path: str = "data/tg9.db") -> None:
        self.db_path = db_path

    async def get_connection(self) -> aiosqlite.Connection:
        """Create and return an active aiosqlite connection with row factory configured."""
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    async def initialize(self) -> None:
        """Create database directory and apply tables and indexes."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        async with await self.get_connection() as conn:
            await conn.executescript(SCHEMA_DDL)
            await conn.commit()

        logger.info("database_initialized", path=self.db_path)
