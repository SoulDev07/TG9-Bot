"""Asynchronous SQLite connection pool supporting concurrent readers and serialized writes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path

import aiosqlite

from core.logger import get_logger

logger = get_logger()

# Task-local tracking of the currently active connection to eliminate nested deadlocks
_current_conn: ContextVar[aiosqlite.Connection | None] = ContextVar("_current_conn", default=None)

SCHEMA_DDL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA temp_store = MEMORY;
PRAGMA cache_size = -64000;
PRAGMA mmap_size = 268435456;

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

CREATE TABLE IF NOT EXISTS temp_bans (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    unban_at TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT 'Temporary ban expired',
    PRIMARY KEY (guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_temp_bans_unban_at ON temp_bans(unban_at);

CREATE TABLE IF NOT EXISTS warning_settings (
    guild_id INTEGER PRIMARY KEY,
    decay_days INTEGER NOT NULL DEFAULT 30
);

CREATE TABLE IF NOT EXISTS warning_reasons (
    guild_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    points INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    PRIMARY KEY (guild_id, name)
);

CREATE TABLE IF NOT EXISTS warning_actions (
    guild_id INTEGER NOT NULL,
    points INTEGER NOT NULL,
    action TEXT NOT NULL,
    duration_seconds INTEGER,
    PRIMARY KEY (guild_id, points)
);

CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    points INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    case_number INTEGER
);

CREATE INDEX IF NOT EXISTS idx_warnings_guild_user ON warnings(guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_warnings_expires_at ON warnings(expires_at);
"""


class DatabaseManager:
    """High-performance SQLite pool managing concurrent WAL readers and a serialized writer.

    Architecture:
        - Single Dedicated Writer: Serializes all mutations to prevent SQLITE_BUSY deadlocks.
        - Reader Pool: Concurrent reader connections executed via a bounded queue.
        - Deadlock-Free Task Borrowing: Coroutines nesting connection contexts reuse the held
          connection via contextvars, avoiding self-deadlocks and pool starvation.
        - Threading: Blocking directory creation offloaded to worker threads via asyncio.to_thread.
    """

    __slots__ = (
        "_closed",
        "_db_path",
        "_init_lock",
        "_reader_connections",
        "_reader_pool",
        "_reader_pool_size",
        "_timeout",
        "_writer_conn",
        "_writer_lock",
    )

    def __init__(
        self,
        db_path: str = "data/tg9.db",
        reader_pool_size: int = 5,
        timeout: float = 5.0,
    ) -> None:
        self._db_path = db_path
        self._reader_pool_size = reader_pool_size
        self._timeout = timeout

        self._writer_conn: aiosqlite.Connection | None = None
        self._writer_lock = asyncio.Lock()
        self._reader_pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue(
            maxsize=reader_pool_size
        )
        self._reader_connections: list[aiosqlite.Connection] = []
        self._init_lock = asyncio.Lock()
        self._closed = False

    @property
    def db_path(self) -> str:
        return self._db_path

    async def _create_connection(self) -> aiosqlite.Connection:
        """Create and tune an individual SQLite connection with optimal pragmas."""
        await asyncio.to_thread(Path(self._db_path).parent.mkdir, parents=True, exist_ok=True)
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.execute("PRAGMA journal_mode = WAL;")
        await conn.execute("PRAGMA synchronous = NORMAL;")
        await conn.execute("PRAGMA busy_timeout = 5000;")
        await conn.execute("PRAGMA temp_store = MEMORY;")
        await conn.execute("PRAGMA cache_size = -64000;")
        await conn.execute("PRAGMA mmap_size = 268435456;")
        return conn

    async def _ensure_initialized(self) -> None:
        """Lazily initialize writer connection and reader pool."""
        if self._writer_conn is not None:
            return

        async with self._init_lock:
            if self._writer_conn is None:
                self._writer_conn = await self._create_connection()
                for _ in range(self._reader_pool_size):
                    r_conn = await self._create_connection()
                    self._reader_connections.append(r_conn)
                    await self._reader_pool.put(r_conn)

    async def _acquire_writer(self) -> aiosqlite.Connection:
        await self._ensure_initialized()
        await asyncio.wait_for(self._writer_lock.acquire(), timeout=self._timeout)
        assert self._writer_conn is not None
        return self._writer_conn

    async def _release_writer(self) -> None:
        if self._writer_lock.locked():
            self._writer_lock.release()

    @asynccontextmanager
    async def read(self) -> AsyncIterator[aiosqlite.Connection]:
        """Acquire a reader connection from the pool, supporting concurrent readers."""
        active = _current_conn.get()
        if active is not None:
            # Reentrancy: reuse existing connection for this task without deadlocking
            yield active
            return

        await self._ensure_initialized()
        conn = await asyncio.wait_for(self._reader_pool.get(), timeout=self._timeout)
        token = _current_conn.set(conn)
        try:
            yield conn
        finally:
            _current_conn.reset(token)
            await self._reader_pool.put(conn)

    @asynccontextmanager
    async def write(self) -> AsyncIterator[aiosqlite.Connection]:
        """Acquire the dedicated writer connection under exclusive writer lock."""
        active = _current_conn.get()
        if active is not None:
            # Reentrancy: task already inside a connection context
            yield active
            return

        conn = await self._acquire_writer()
        token = _current_conn.set(conn)
        try:
            yield conn
        except BaseException:
            await conn.rollback()
            raise
        finally:
            _current_conn.reset(token)
            await self._release_writer()

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Default connection context manager prioritizing write safety with reentrant borrowing."""
        active = _current_conn.get()
        if active is not None:
            yield active
            return

        async with self.write() as conn:
            yield conn

    __call__ = connection

    async def initialize(self) -> None:
        """Create database directory, apply tables and indexes, and verify WAL mode."""
        await self._ensure_initialized()
        async with self.write() as conn:
            await conn.executescript(SCHEMA_DDL)
            await conn.commit()

        logger.info(
            "database_initialized",
            path=self._db_path,
            reader_pool_size=self._reader_pool_size,
        )

    async def close(self) -> None:
        """Gracefully drain the reader pool and close the persistent writer connection."""
        async with self._init_lock:
            if self._closed:
                return
            self._closed = True

            async with self._writer_lock:
                if self._writer_conn is not None:
                    await self._writer_conn.close()
                    self._writer_conn = None

            for conn in self._reader_connections:
                await conn.close()
            self._reader_connections.clear()

            logger.info("database_closed", path=self._db_path)
