"""Domain service handling message purging and cleanup predicates."""

from __future__ import annotations

from collections.abc import Callable

import discord

type MessageableChannel = discord.TextChannel | discord.Thread | discord.VoiceChannel


async def purge_channel(
    channel: MessageableChannel,
    amount: int,
    check: Callable[[discord.Message], bool] | None = None,
    after: discord.Object | None = None,
    reason: str | None = None,
) -> int:
    """Purge a specified number of messages from a channel with optional filtering predicate."""
    purged = await channel.purge(limit=amount, check=check, after=after, reason=reason)
    return len(purged)


async def purge_user_messages(
    channel: MessageableChannel,
    user_id: int,
    amount: int,
    reason: str | None = None,
) -> int:
    """Purge messages sent exclusively by a target user."""
    return await purge_channel(
        channel,
        amount=amount,
        check=lambda m: m.author.id == user_id,
        reason=reason,
    )


async def purge_bot_messages(
    channel: MessageableChannel,
    amount: int,
    prefix: str = "!",
    reason: str | None = None,
) -> int:
    """Purge messages sent by bots, prefix commands, or application interactions."""

    def is_bot_or_command(m: discord.Message) -> bool:
        if m.author.bot or m.interaction is not None:
            return True
        content = m.content.strip()
        return bool(content and (content.startswith(prefix) or content.startswith("/")))

    return await purge_channel(
        channel,
        amount=amount,
        check=is_bot_or_command,
        reason=reason,
    )


async def purge_containing_text(
    channel: MessageableChannel,
    text: str,
    amount: int,
    reason: str | None = None,
) -> int:
    """Purge messages containing a specific substring or keywords."""
    needle = text.lower()
    return await purge_channel(
        channel,
        amount=amount,
        check=lambda m: needle in m.content.lower(),
        reason=reason,
    )


async def purge_embed_messages(
    channel: MessageableChannel,
    amount: int,
    reason: str | None = None,
) -> int:
    """Purge messages containing rich embeds or link previews."""
    return await purge_channel(
        channel,
        amount=amount,
        check=lambda m: bool(m.embeds),
        reason=reason,
    )


async def purge_file_messages(
    channel: MessageableChannel,
    amount: int,
    reason: str | None = None,
) -> int:
    """Purge messages containing file attachments or uploaded media."""
    return await purge_channel(
        channel,
        amount=amount,
        check=lambda m: bool(m.attachments),
        reason=reason,
    )


async def purge_messages_after(
    channel: MessageableChannel,
    message_id: int,
    limit: int = 500,
    reason: str | None = None,
) -> int:
    """Purge all messages sent between target message ID and the current time."""
    after_obj = discord.Object(id=message_id)
    return await purge_channel(
        channel,
        amount=limit,
        after=after_obj,
        reason=reason,
    )
