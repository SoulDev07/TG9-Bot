"""Integration tests for DatabaseManager SQLite connection pool and WAL concurrency."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from helpers.db.database import DatabaseManager


@pytest.fixture
async def db_manager(tmp_path: Path):
    """Fixture providing a temporary, fully initialized DatabaseManager."""
    db_file = tmp_path / "test.db"
    manager = DatabaseManager(db_path=str(db_file), reader_pool_size=4)
    await manager.initialize()
    yield manager
    await manager.close()


@pytest.mark.asyncio
async def test_database_initialization(db_manager: DatabaseManager) -> None:
    """Verify that the database initializes and sets WAL journal mode."""
    async with db_manager.read() as conn:
        cursor = await conn.execute("PRAGMA journal_mode;")
        row = await cursor.fetchone()
        assert row is not None
        assert row[0].lower() == "wal"


@pytest.mark.asyncio
async def test_concurrent_readers(db_manager: DatabaseManager) -> None:
    """Verify that multiple concurrent readers execute in parallel without blocking."""

    async def reader_task(reader_id: int) -> int:
        async with db_manager.read() as conn:
            cursor = await conn.execute("SELECT ? AS val;", (reader_id,))
            row = await cursor.fetchone()
            assert row is not None
            return row["val"]

    results = await asyncio.gather(*(reader_task(i) for i in range(10)))
    assert results == list(range(10))


@pytest.mark.asyncio
async def test_serialized_writer_transactions(db_manager: DatabaseManager) -> None:
    """Verify that writer mutations execute cleanly and commit data."""
    async with db_manager.write() as conn:
        await conn.execute(
            """
            INSERT INTO blacklist (user_id, reason, created_at, created_by)
            VALUES (?, ?, ?, ?)
            """,
            (1001, "Test blacklisted user", "2026-10-26T00:00:00Z", 9999),
        )
        await conn.commit()

    async with db_manager.read() as conn:
        cursor = await conn.execute("SELECT reason FROM blacklist WHERE user_id = 1001;")
        row = await cursor.fetchone()
        assert row is not None
        assert row["reason"] == "Test blacklisted user"


@pytest.mark.asyncio
async def test_task_local_reentrant_borrowing(db_manager: DatabaseManager) -> None:
    """Verify that nested connection contexts in the same task borrow without deadlocking."""
    async with db_manager.write() as outer_conn:  # noqa: SIM117
        # Deliberately nested write context to verify task-local borrowing
        async with db_manager.write() as inner_conn:
            assert outer_conn is inner_conn
            # Deliberately nested read context to verify task-local borrowing
            async with db_manager.read() as read_conn:
                assert read_conn is outer_conn
                cursor = await read_conn.execute("SELECT 42 AS num;")
                row = await cursor.fetchone()
                assert row is not None
                assert row["num"] == 42
