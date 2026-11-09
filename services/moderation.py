"""Domain service handling business logic, execution, and audit logging for moderation actions."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

import discord
from discord.ext.commands import Context

from helpers.checks import get_audit_reason
from helpers.embeds import modlog_case_embed
from helpers.hierarchy import validate_hierarchy
from helpers.logger import get_logger

if TYPE_CHECKING:
    from helpers.db.models import ModCase

logger = get_logger()

_background_tasks: set[asyncio.Task[None]] = set()


def validate_target(ctx: Context, member: discord.Member) -> None:
    """Enforce role hierarchy and protection rules against target member."""
    validate_hierarchy(ctx, member)


async def _dispatch_modlog(
    ctx: Context,
    case: ModCase,
    target: discord.Member | discord.User,
) -> None:
    """Background task to deliver and persist the modlog audit case embed."""
    try:
        settings = await ctx.bot.guild_repo.get(ctx.guild.id)
        if not settings or not settings.modlog_channel_id:
            return

        channel = ctx.guild.get_channel(settings.modlog_channel_id)
        if not isinstance(channel, discord.TextChannel | discord.Thread):
            return

        embed = modlog_case_embed(case, user=target, moderator=ctx.author)
        message = await channel.send(embed=embed)
        await ctx.bot.mod_case_repo.update_message_id(ctx.guild.id, case.case_number, message.id)
    except Exception as exc:
        logger.warning(
            "modlog_dispatch_failed",
            guild_id=ctx.guild.id,
            case_number=case.case_number,
            error=str(exc),
        )


async def record_case(
    ctx: Context,
    action: str,
    target: discord.Member | discord.User,
    reason: str,
) -> ModCase:
    """Record a moderation case in the database and dispatch audit log asynchronously."""
    case = await ctx.bot.mod_case_repo.create_case(
        guild_id=ctx.guild.id,
        action=action,
        user_id=target.id,
        moderator_id=ctx.author.id,
        reason=reason,
    )
    # Fire and forget modlog dispatch to avoid blocking command completion
    task = asyncio.create_task(_dispatch_modlog(ctx, case, target))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return case


async def edit_case_reason(
    ctx: Context,
    case_number: int,
    new_reason: str,
) -> tuple[bool, str, ModCase | None]:
    """Update a case's reason in SQLite and live-edit its audit log embed in Discord."""
    case = await ctx.bot.mod_case_repo.get_case(ctx.guild.id, case_number)
    if not case:
        return False, f"Case #{case_number} was not found for this server.", None

    await ctx.bot.mod_case_repo.update_reason(ctx.guild.id, case_number, new_reason)
    updated_case = case.model_copy(update={"reason": new_reason})

    settings = await ctx.bot.guild_repo.get(ctx.guild.id)
    if settings and settings.modlog_channel_id and case.message_id:
        channel = ctx.guild.get_channel(settings.modlog_channel_id)
        if isinstance(channel, discord.TextChannel | discord.Thread):
            with contextlib.suppress(discord.NotFound, discord.Forbidden, discord.HTTPException):
                msg = await channel.fetch_message(case.message_id)
                target = ctx.guild.get_member(case.user_id) or await ctx.bot.fetch_user(
                    case.user_id
                )
                mod = ctx.guild.get_member(case.moderator_id) or await ctx.bot.fetch_user(
                    case.moderator_id
                )
                embed = modlog_case_embed(updated_case, user=target, moderator=mod)
                await msg.edit(embed=embed)

    return True, f"Case #{case_number} reason has been successfully updated.", updated_case


async def warn_member(
    ctx: Context,
    member: discord.Member,
    reason: str,
) -> ModCase:
    """Validate hierarchy, notify member via DM, and record the case."""
    validate_target(ctx, member)
    with contextlib.suppress(discord.Forbidden, discord.HTTPException):
        await member.send(
            f"You were warned in **{ctx.guild.name}** by **{ctx.author}**!\nReason: {reason}"
        )
    return await record_case(ctx, action="warn", target=member, reason=reason)


async def kick_member(
    ctx: Context,
    member: discord.Member,
    reason: str,
) -> ModCase:
    """Validate hierarchy, notify member, perform guild kick, and record the case."""
    validate_target(ctx, member)
    audit_reason = get_audit_reason(ctx.author, reason)

    with contextlib.suppress(discord.Forbidden, discord.HTTPException):
        await member.send(
            f"You were kicked from **{ctx.guild.name}** by **{ctx.author}**!\nReason: {reason}"
        )

    await member.kick(reason=audit_reason)
    return await record_case(ctx, action="kick", target=member, reason=reason)


async def ban_member(
    ctx: Context,
    member: discord.Member,
    reason: str,
) -> ModCase:
    """Validate hierarchy, notify member, perform guild ban, and record the case."""
    validate_target(ctx, member)
    audit_reason = get_audit_reason(ctx.author, reason)

    with contextlib.suppress(discord.Forbidden, discord.HTTPException):
        await member.send(
            f"You were banned from **{ctx.guild.name}** by **{ctx.author}**!\nReason: {reason}"
        )

    await member.ban(reason=audit_reason)
    return await record_case(ctx, action="ban", target=member, reason=reason)


async def purge_channel(
    channel: discord.TextChannel | discord.Thread | discord.VoiceChannel,
    amount: int,
) -> int:
    """Purge a specified number of messages from a channel."""
    purged = await channel.purge(limit=amount)
    return len(purged)
