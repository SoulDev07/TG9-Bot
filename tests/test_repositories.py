"""Integration tests for SQLite persistence repositories."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from helpers.db.blacklist_repo import BlacklistRepository
from helpers.db.database import DatabaseManager
from helpers.db.guild_repo import GuildRepository
from helpers.db.modcase_repo import ModCaseRepository
from helpers.db.tempban_repo import TempBanRepository
from helpers.db.warning_repo import WarningRepository


@pytest.fixture
async def db(tmp_path: Path):
    """Fixture providing an initialized DatabaseManager."""
    db_file = tmp_path / "repo_test.db"
    manager = DatabaseManager(db_path=str(db_file), reader_pool_size=4)
    await manager.initialize()
    yield manager
    await manager.close()


@pytest.mark.asyncio
async def test_guild_repository_flow(db: DatabaseManager) -> None:
    """Test guild settings creation, prefix update, and module enablement."""
    repo = GuildRepository(db)
    guild_id = 1234567890

    # Create / get default settings
    settings = await repo.get_or_create(guild_id, default_prefix="!")
    assert settings.guild_id == guild_id
    assert settings.prefix == "!"

    # Update prefix
    await repo.update_prefix(guild_id, "?")
    prefix = await repo.get_prefix(guild_id)
    assert prefix == "?"

    # Module toggles
    is_mod_enabled = await repo.is_module_enabled(guild_id, "moderation")
    assert is_mod_enabled is True

    await repo.set_module_enabled(guild_id, "moderation", enabled=False)
    assert await repo.is_module_enabled(guild_id, "moderation") is False

    await repo.set_module_enabled(guild_id, "moderation", enabled=True)
    assert await repo.is_module_enabled(guild_id, "moderation") is True

    # Role configuration
    await repo.add_role(guild_id, role_id=999, role_type="admin")
    admin_roles = await repo.get_roles(guild_id, "admin")
    assert 999 in admin_roles

    await repo.remove_role(guild_id, role_id=999, role_type="admin")
    admin_roles = await repo.get_roles(guild_id, "admin")
    assert 999 not in admin_roles


@pytest.mark.asyncio
async def test_blacklist_repository_flow(db: DatabaseManager) -> None:
    """Test global user blacklisting, verification, and unblacklisting."""
    repo = BlacklistRepository(db)
    target_user_id = 555666777

    assert await repo.is_blacklisted(target_user_id) is False

    await repo.add(target_user_id, reason="Malicious user", created_by=1)
    assert await repo.is_blacklisted(target_user_id) is True
    assert await repo.count() == 1

    entry = await repo.get(target_user_id)
    assert entry is not None
    assert entry.reason == "Malicious user"

    removed = await repo.remove(target_user_id)
    assert removed is True
    assert await repo.is_blacklisted(target_user_id) is False
    assert await repo.count() == 0


@pytest.mark.asyncio
async def test_mod_case_repository_flow(db: DatabaseManager) -> None:
    """Test sequential case assignment, reason live updates, and case queries."""
    repo = ModCaseRepository(db)
    guild_id = 8888

    case1 = await repo.create_case(
        guild_id=guild_id,
        action="warn",
        user_id=101,
        moderator_id=1,
        reason="First warning",
    )
    assert case1.case_number == 1

    case2 = await repo.create_case(
        guild_id=guild_id,
        action="kick",
        user_id=101,
        moderator_id=1,
        reason="Repeated spam",
    )
    assert case2.case_number == 2

    # Reason edit
    await repo.update_reason(guild_id, case_number=1, reason="Updated first warning")
    fetched_case = await repo.get_case(guild_id, case_number=1)
    assert fetched_case is not None
    assert fetched_case.reason == "Updated first warning"

    # User cases
    user_cases = await repo.get_cases_for_user(guild_id, user_id=101)
    assert len(user_cases) == 2
    assert user_cases[0].case_number == 2  # Newest first


@pytest.mark.asyncio
async def test_tempban_repository_flow(db: DatabaseManager) -> None:
    """Test scheduling, query, and expiration detection of temporary bans."""
    repo = TempBanRepository(db)
    guild_id = 9999
    user_id = 202

    now = datetime.now(UTC)
    unban_time = now + timedelta(hours=1)

    await repo.add_tempban(guild_id, user_id, unban_at=unban_time, reason="1 hour ban")
    fetched_unban = await repo.get_tempban(guild_id, user_id)
    assert fetched_unban is not None

    # Before expiration: should not be returned as expired
    expired = await repo.get_expired_tempbans(now)
    assert not any(u == user_id for _, u, _ in expired)

    # After expiration: should be returned as expired
    future = now + timedelta(hours=2)
    expired = await repo.get_expired_tempbans(future)
    assert any(u == user_id for _, u, _ in expired)

    removed = await repo.remove_tempban(guild_id, user_id)
    assert removed is True
    assert await repo.get_tempban(guild_id, user_id) is None


@pytest.mark.asyncio
async def test_warning_repository_flow(db: DatabaseManager) -> None:
    """Test warning records, active point calculation, point decay, and action thresholds."""
    repo = WarningRepository(db)
    guild_id = 7777
    user_id = 303
    mod_id = 1

    # Settings and decay
    settings = await repo.get_settings(guild_id)
    assert settings.decay_days == 30

    await repo.set_decay(guild_id, decay_days=14)
    updated_settings = await repo.get_settings(guild_id)
    assert updated_settings.decay_days == 14

    # Default action thresholds: 3 -> timeout, 5 -> kick, 10 -> ban
    actions = await repo.get_actions(guild_id)
    assert len(actions) == 3
    assert actions[0].points == 3
    assert actions[0].action == "timeout"

    # Add custom threshold
    await repo.set_action(guild_id, points=2, action="timeout", duration_seconds=1800)
    updated_actions = await repo.get_actions(guild_id)
    assert any(a.points == 2 for a in updated_actions)

    await repo.delete_action(guild_id, points=2)
    updated_actions = await repo.get_actions(guild_id)
    assert not any(a.points == 2 for a in updated_actions)

    # Issue warnings
    now = datetime.now(UTC)
    active_warning = await repo.create_warning(
        guild_id=guild_id,
        user_id=user_id,
        moderator_id=mod_id,
        reason="Spam",
        points=2,
        expires_at=now + timedelta(days=7),
    )
    assert active_warning.points == 2

    # Expired warning (in the past)
    await repo.create_warning(
        guild_id=guild_id,
        user_id=user_id,
        moderator_id=mod_id,
        reason="Old offense",
        points=3,
        expires_at=now - timedelta(days=1),
    )

    # Active points should only sum non-expired warning points (2 points, not 5)
    active_points = await repo.get_active_points(guild_id, user_id, now=now)
    assert active_points == 2

    # Get warnings
    all_warnings = await repo.get_warnings(guild_id, user_id, active_only=False)
    assert len(all_warnings) == 2

    active_warnings = await repo.get_warnings(guild_id, user_id, active_only=True, now=now)
    assert len(active_warnings) == 1
    assert active_warnings[0].id == active_warning.id

    # Delete warning
    deleted = await repo.delete_warning(guild_id, active_warning.id)
    assert deleted is True
    assert await repo.get_active_points(guild_id, user_id, now=now) == 0
