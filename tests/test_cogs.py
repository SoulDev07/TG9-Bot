"""Tests verifying that all extension cogs load and instantiate properly."""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

from cogs.cases import Cases
from cogs.cleanup import Cleanup
from cogs.fun import Fun
from cogs.general import General
from cogs.help import Help
from cogs.moderation import Moderation
from cogs.owner import Owner
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
        Cases(mock_bot),
        Cleanup(mock_bot),
        Fun(mock_bot),
        General(mock_bot),
        Help(mock_bot),
        Moderation(mock_bot),
        Owner(mock_bot),
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

    # Check that new commands are registered on Moderation cog
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

    # Check General commands
    gen_cog = General(mock_bot)
    gen_cmd_names = {c.name for c in gen_cog.get_commands()}
    assert "userinfo" in gen_cmd_names
    assert "serverinfo" in gen_cmd_names
    assert "avatar" in gen_cmd_names

    # Check Fun commands
    fun_cog = Fun(mock_bot)
    fun_cmd_names = {c.name for c in fun_cog.get_commands()}
    assert "roll" in fun_cmd_names
    assert "8ball" in fun_cmd_names

    # Check Owner commands
    owner_cog = Owner(mock_bot)
    owner_cmd_names = {c.name for c in owner_cog.get_commands()}
    assert "sync" in owner_cmd_names
    assert "cogs" in owner_cmd_names
    assert "shutdown" in owner_cmd_names
    assert "eval" not in owner_cmd_names

    # Check command aliases
    owner_map = {c.name: c for c in owner_cog.get_commands()}
    assert "extensions" in owner_map["cogs"].aliases
    assert "modules" in owner_map["cogs"].aliases
    assert "sd" in owner_map["shutdown"].aliases

    mod_map = {c.name: c for c in mod_cog.get_commands()}
    assert "echo" in mod_map["say"].aliases
    assert "role" in mod_map["roles"].aliases
    assert "sm" in mod_map["slowmode"].aliases
    assert "broadcast" in mod_map["announce"].aliases

    gen_map = {c.name: c for c in gen_cog.get_commands()}
    assert "botinfo" in gen_map["info"].aliases
    assert "latency" in gen_map["ping"].aliases
    assert "support" in gen_map["server"].aliases
