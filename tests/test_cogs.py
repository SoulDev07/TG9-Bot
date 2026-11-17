"""Tests verifying that all extension cogs load and instantiate properly."""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

from cogs.builder import Builder
from cogs.cases import Cases
from cogs.cleanup import Cleanup
from cogs.fun import Fun
from cogs.general import General
from cogs.help import Help
from cogs.moderation import Moderation
from cogs.owner import Owner
from cogs.reminders import Reminders
from cogs.setup import Setup
from cogs.warnings import Warnings


@pytest.mark.asyncio
async def test_cog_instantiation() -> None:
    """Verify all cogs instantiate without error given a mock bot instance."""
    mock_bot = MagicMock()
    mock_bot.config.prefix = "!"
    mock_bot.config.statuses = []
    mock_bot.config.is_owner.return_value = True

    cogs = [
        Builder(mock_bot),
        Cases(mock_bot),
        Cleanup(mock_bot),
        Fun(mock_bot),
        General(mock_bot),
        Help(mock_bot),
        Moderation(mock_bot),
        Owner(mock_bot),
        Reminders(mock_bot),
        Setup(mock_bot),
        Warnings(mock_bot),
    ]

    for cog in cogs:
        assert cog is not None
        assert len(cog.get_commands()) > 0
        if hasattr(cog, "cog_unload"):
            unload_res = cog.cog_unload()
            if inspect.isawaitable(unload_res):
                await unload_res

    mod_cog = Moderation(mock_bot)
    mod_cmd_names = {c.name for c in mod_cog.get_commands()}
    assert "slowmode" in mod_cmd_names
    assert "announce" in mod_cmd_names
    assert "selfroles" in mod_cmd_names
    assert "selfrole" in mod_cmd_names
    assert "timeout" in mod_cmd_names
    assert "untimeout" in mod_cmd_names
    if hasattr(mod_cog, "cog_unload"):
        unload_res = mod_cog.cog_unload()
        if inspect.isawaitable(unload_res):
            await unload_res

    gen_cog = General(mock_bot)
    gen_cmd_names = {c.name for c in gen_cog.get_commands()}
    assert "userinfo" in gen_cmd_names
    assert "serverinfo" in gen_cmd_names
    assert "avatar" in gen_cmd_names

    fun_cog = Fun(mock_bot)
    fun_cmd_names = {c.name for c in fun_cog.get_commands()}
    assert "roll" in fun_cmd_names
    assert "8ball" in fun_cmd_names

    owner_cog = Owner(mock_bot)
    owner_cmd_names = {c.name for c in owner_cog.get_commands()}
    assert "sync" in owner_cmd_names
    assert "cogs" in owner_cmd_names
    assert "shutdown" in owner_cmd_names
    assert "eval" not in owner_cmd_names

    owner_map = {c.name: c for c in owner_cog.get_commands()}
    assert "extensions" in owner_map["cogs"].aliases
    assert "sd" in owner_map["shutdown"].aliases

    setup_cog = Setup(mock_bot)
    setup_map = {c.name: c for c in setup_cog.get_commands()}
    assert "config" in setup_map["settings"].aliases

    mod_map = {c.name: c for c in mod_cog.get_commands()}
    assert "echo" in mod_map["say"].aliases
    assert "role" in mod_map["roles"].aliases
    assert "sm" in mod_map["slowmode"].aliases
    assert "broadcast" in mod_map["announce"].aliases

    gen_map = {c.name: c for c in gen_cog.get_commands()}
    assert "botinfo" in gen_map["info"].aliases
    assert "latency" in gen_map["ping"].aliases
    assert "support" in gen_map["server"].aliases

    builder_cog = Builder(mock_bot)
    builder_cmd_names = {c.name for c in builder_cog.get_commands()}
    assert "builder" in builder_cmd_names
    assert "edit" in builder_cmd_names
    builder_map = {c.name: c for c in builder_cog.get_commands()}
    assert "embedbuilder" in builder_map["builder"].aliases

    reminders_cog = Reminders(mock_bot)
    reminders_cmd_names = {c.name for c in reminders_cog.get_commands()}
    assert "remindme" in reminders_cmd_names
    assert "reminders" in reminders_cmd_names
    assert "remindrepeat" in reminders_cmd_names
    reminders_map = {c.name: c for c in reminders_cog.get_commands()}
    assert "timer" in reminders_map["remindme"].aliases
    assert "remind" in reminders_map["remindme"].aliases
    assert "remindlist" in reminders_map["reminders"].aliases
    assert "recurring" in reminders_map["remindrepeat"].aliases
    if hasattr(reminders_cog, "cog_unload"):
        unload_res = reminders_cog.cog_unload()
        if inspect.isawaitable(unload_res):
            await unload_res
