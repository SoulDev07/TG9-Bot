"""Unit tests for moderation purge and cleanup suite."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from services.moderation import (
    purge_bot_messages,
    purge_channel,
    purge_containing_text,
    purge_embed_messages,
    purge_file_messages,
    purge_messages_after,
    purge_user_messages,
)


def _make_mock_message(
    user_id: int = 100,
    is_bot: bool = False,
    content: str = "hello world",
    embeds: list | None = None,
    attachments: list | None = None,
    interaction: object = None,
) -> MagicMock:
    """Helper creating a mock Discord message."""
    msg = MagicMock(spec=discord.Message)
    msg.author = MagicMock()
    msg.author.id = user_id
    msg.author.bot = is_bot
    msg.content = content
    msg.embeds = embeds or []
    msg.attachments = attachments or []
    msg.interaction = interaction
    return msg


@pytest.mark.asyncio
async def test_purge_channel_basic() -> None:
    """Verify purge_channel calls channel.purge and returns count."""
    channel = AsyncMock(spec=discord.TextChannel)
    channel.purge.return_value = [MagicMock(), MagicMock(), MagicMock()]

    count = await purge_channel(channel, amount=10, reason="test purge")
    assert count == 3
    channel.purge.assert_awaited_once_with(limit=10, check=None, after=None, reason="test purge")


@pytest.mark.asyncio
async def test_purge_user_messages() -> None:
    """Verify purge_user_messages filters by target user ID."""
    channel = AsyncMock(spec=discord.TextChannel)
    target_id = 42

    async def fake_purge(limit, check, after, reason):
        messages = [
            _make_mock_message(user_id=42, content="target 1"),
            _make_mock_message(user_id=99, content="other user"),
            _make_mock_message(user_id=42, content="target 2"),
        ]
        return [m for m in messages if check(m)]

    channel.purge.side_effect = fake_purge

    count = await purge_user_messages(channel, user_id=target_id, amount=50)
    assert count == 2


@pytest.mark.asyncio
async def test_purge_bot_messages() -> None:
    """Verify purge_bot_messages filters bots, slash commands, and prefix invocations."""
    channel = AsyncMock(spec=discord.TextChannel)

    async def fake_purge(limit, check, after, reason):
        messages = [
            _make_mock_message(is_bot=True, content="I am a bot"),
            _make_mock_message(is_bot=False, content="!help"),
            _make_mock_message(is_bot=False, content="regular user chat"),
            _make_mock_message(is_bot=False, content="", interaction=MagicMock()),
        ]
        return [m for m in messages if check(m)]

    channel.purge.side_effect = fake_purge

    count = await purge_bot_messages(channel, amount=50, prefix="!")
    assert count == 3


@pytest.mark.asyncio
async def test_purge_containing_text() -> None:
    """Verify purge_containing_text matches substring case-insensitively."""
    channel = AsyncMock(spec=discord.TextChannel)

    async def fake_purge(limit, check, after, reason):
        messages = [
            _make_mock_message(content="Click this Free Discord Nitro scam link!"),
            _make_mock_message(content="Nitro is cool"),
            _make_mock_message(content="Normal message"),
        ]
        return [m for m in messages if check(m)]

    channel.purge.side_effect = fake_purge

    count = await purge_containing_text(channel, text="nitro", amount=50)
    assert count == 2


@pytest.mark.asyncio
async def test_purge_embed_messages() -> None:
    """Verify purge_embed_messages matches messages containing embeds."""
    channel = AsyncMock(spec=discord.TextChannel)

    async def fake_purge(limit, check, after, reason):
        messages = [
            _make_mock_message(content="has embed", embeds=[MagicMock()]),
            _make_mock_message(content="no embed", embeds=[]),
        ]
        return [m for m in messages if check(m)]

    channel.purge.side_effect = fake_purge

    count = await purge_embed_messages(channel, amount=50)
    assert count == 1


@pytest.mark.asyncio
async def test_purge_file_messages() -> None:
    """Verify purge_file_messages matches messages containing file attachments."""
    channel = AsyncMock(spec=discord.TextChannel)

    async def fake_purge(limit, check, after, reason):
        messages = [
            _make_mock_message(content="image attachment", attachments=[MagicMock()]),
            _make_mock_message(content="plain text", attachments=[]),
        ]
        return [m for m in messages if check(m)]

    channel.purge.side_effect = fake_purge

    count = await purge_file_messages(channel, amount=50)
    assert count == 1


@pytest.mark.asyncio
async def test_purge_messages_after() -> None:
    """Verify purge_messages_after passes target after object."""
    channel = AsyncMock(spec=discord.TextChannel)
    channel.purge.return_value = [MagicMock(), MagicMock()]

    count = await purge_messages_after(channel, message_id=123456789, limit=100)
    assert count == 2
    assert channel.purge.call_args.kwargs["after"].id == 123456789
