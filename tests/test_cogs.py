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
