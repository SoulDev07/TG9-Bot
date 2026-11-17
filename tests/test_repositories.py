"""Integration tests for SQLite persistence repositories."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.db import (
    BlacklistRepository,
    CaseRepository,
    DatabaseManager,
    GuildRepository,
    ReminderRepository,
    TempBanRepository,
    WarningRepository,
)


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

    settings = await repo.get_or_create(guild_id, default_prefix="!")
    assert settings.guild_id == guild_id
    assert settings.prefix == "!"

    await repo.update_prefix(guild_id, "?")
    prefix = await repo.get_prefix(guild_id)
    assert prefix == "?"

    is_mod_enabled = await repo.is_module_enabled(guild_id, "moderation")
    assert is_mod_enabled is True

    await repo.set_module_enabled(guild_id, "moderation", enabled=False)
    assert await repo.is_module_enabled(guild_id, "moderation") is False

    await repo.set_module_enabled(guild_id, "moderation", enabled=True)
    assert await repo.is_module_enabled(guild_id, "moderation") is True

    await repo.add_role(guild_id, role_id=999, role_type="admin")
    admin_roles = await repo.get_roles(guild_id, "admin")
    assert 999 in admin_roles

    await repo.remove_role(guild_id, role_id=999, role_type="admin")
    admin_roles = await repo.get_roles(guild_id, "admin")
    assert 999 not in admin_roles

    await repo.add_role(guild_id, role_id=888, role_type="selfrole")
    self_roles = await repo.get_roles(guild_id, "selfrole")
    assert 888 in self_roles

    all_roles = await repo.get_all_roles(guild_id)
    assert 888 in all_roles.get("selfrole", set())

    removed_self = await repo.remove_role(guild_id, role_id=888, role_type="selfrole")
    assert removed_self is True
    self_roles_after = await repo.get_roles(guild_id, "selfrole")
    assert 888 not in self_roles_after


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
async def test_case_repository_flow(db: DatabaseManager) -> None:
    """Test sequential case assignment, reason live updates, and case queries."""
    repo = CaseRepository(db)
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

    await repo.update_reason(guild_id, case_number=1, reason="Updated first warning")
    fetched_case = await repo.get_case(guild_id, case_number=1)
    assert fetched_case is not None
    assert fetched_case.reason == "Updated first warning"

    user_cases = await repo.get_cases_for_user(guild_id, user_id=101)
    assert len(user_cases) == 2
    assert user_cases[0].case_number == 2


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

    expired = await repo.get_expired_tempbans(now)
    assert not any(u == user_id for _, u, _ in expired)

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

    settings = await repo.get_settings(guild_id)
    assert settings.decay_days == 30

    await repo.set_decay(guild_id, decay_days=14)
    updated_settings = await repo.get_settings(guild_id)
    assert updated_settings.decay_days == 14

    actions = await repo.get_actions(guild_id)
    assert len(actions) == 3
    assert actions[0].points == 3
    assert actions[0].action == "timeout"

    await repo.set_action(guild_id, points=2, action="timeout", duration_seconds=1800)
    updated_actions = await repo.get_actions(guild_id)
    assert any(a.points == 2 for a in updated_actions)

    await repo.delete_action(guild_id, points=2)
    updated_actions = await repo.get_actions(guild_id)
    assert not any(a.points == 2 for a in updated_actions)

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

    await repo.create_warning(
        guild_id=guild_id,
        user_id=user_id,
        moderator_id=mod_id,
        reason="Old offense",
        points=3,
        expires_at=now - timedelta(days=1),
    )

    active_points = await repo.get_active_points(guild_id, user_id, now=now)
    assert active_points == 2

    all_warnings = await repo.get_warnings(guild_id, user_id, active_only=False)
    assert len(all_warnings) == 2

    active_warnings = await repo.get_warnings(guild_id, user_id, active_only=True, now=now)
    assert len(active_warnings) == 1
    assert active_warnings[0].id == active_warning.id

    deleted = await repo.delete_warning(guild_id, active_warning.id)
    assert deleted is True
    assert await repo.get_active_points(guild_id, user_id, now=now) == 0


@pytest.mark.asyncio
async def test_reminder_repository_flow(db: DatabaseManager) -> None:
    """Test creating reminders, querying due reminders, updating recurring, and deletion."""
    repo = ReminderRepository(db)
    user_id = 111222333
    guild_id = 999888777
    channel_id = 444555666

    now = datetime.now(UTC)
    due_time = now - timedelta(minutes=5)
    future_time = now + timedelta(hours=2)

    r1 = await repo.create_reminder(
        user_id=user_id,
        guild_id=guild_id,
        channel_id=channel_id,
        message="Take out the trash",
        remind_at=due_time,
    )
    assert r1.id is not None
    assert r1.message == "Take out the trash"

    r2 = await repo.create_reminder(
        user_id=user_id,
        guild_id=None,
        channel_id=None,
        message="Doctor appointment",
        remind_at=future_time,
        repeat_interval_seconds=86400,
    )
    assert r2.id is not None
    assert r2.repeat_interval_seconds == 86400

    user_rems = await repo.get_user_reminders(user_id)
    assert len(user_rems) == 2

    due = await repo.get_due_reminders(now)
    assert len(due) == 1
    assert due[0].id == r1.id

    new_due = now + timedelta(days=1)
    updated = await repo.update_remind_at(r2.id, new_due)
    assert updated is True

    fetched_r2 = await repo.get_reminder(r2.id)
    assert fetched_r2 is not None
    assert fetched_r2.remind_at == new_due

    deleted = await repo.delete_reminder(r1.id, user_id=user_id)
    assert deleted is True
    assert await repo.get_reminder(r1.id) is None
    assert len(await repo.get_user_reminders(user_id)) == 1
