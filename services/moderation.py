"""Domain service handling business logic, execution, and audit logging for moderation actions."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord
import humanize
from discord.ext.commands import Context

from helpers.checks import get_audit_reason
from helpers.embeds import modlog_case_embed
from helpers.exceptions import HierarchyError
from helpers.hierarchy import validate_hierarchy
from helpers.logger import get_logger

if TYPE_CHECKING:
    from helpers.db.models import ModCase, WarningAction, WarningRecord

logger = get_logger()

_background_tasks: set[asyncio.Task[None]] = set()


def validate_target(ctx: Context, member: discord.Member) -> None:
    """Enforce role hierarchy and protection rules against target member."""
    validate_hierarchy(ctx, member)


async def _dispatch_modlog(
    ctx: Context,
    case: ModCase,
    target: discord.Member | discord.User | discord.Object,
) -> None:
    """Background task to deliver and persist the modlog audit case embed."""
    try:
        settings = await ctx.bot.guild_repo.get(ctx.guild.id)
        if not settings or not settings.modlog_channel_id:
            return

        channel = ctx.guild.get_channel(settings.modlog_channel_id)
        if not isinstance(channel, discord.TextChannel | discord.Thread):
            return

        user_display: discord.User | discord.Member | None = None
        if isinstance(target, discord.Member | discord.User):
            user_display = target
        else:
            with contextlib.suppress(discord.HTTPException):
                user_display = await ctx.bot.fetch_user(target.id)

        embed = modlog_case_embed(case, user=user_display, moderator=ctx.author)
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
    target: discord.Member | discord.User | discord.Object,
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
    reason: str = "Not specified",
    points: int | None = None,
) -> tuple[ModCase, WarningRecord, int, WarningAction | None]:
    """Validate hierarchy, record warning points, trigger automated escalations, and audit log."""
    validate_target(ctx, member)

    # Resolve points from preset reasons if not explicitly specified
    if points is None:
        matched_reason = await ctx.bot.warning_repo.get_reason(ctx.guild.id, reason)
        resolved_points = matched_reason.points if matched_reason else 1
    else:
        resolved_points = max(1, points)

    now = datetime.now(UTC)
    settings = await ctx.bot.warning_repo.get_settings(ctx.guild.id)
    expires_at = now + timedelta(days=settings.decay_days) if settings.decay_days > 0 else None

    # Fetch pre-warning accumulated points
    prev_points = await ctx.bot.warning_repo.get_active_points(ctx.guild.id, member.id, now=now)
    new_points = prev_points + resolved_points

    case_reason = f"{reason} (+{resolved_points} pt{'s' if resolved_points != 1 else ''})"
    case = await record_case(ctx, action="warn", target=member, reason=case_reason)

    warning_record = await ctx.bot.warning_repo.create_warning(
        guild_id=ctx.guild.id,
        user_id=member.id,
        moderator_id=ctx.author.id,
        reason=reason,
        points=resolved_points,
        expires_at=expires_at,
        case_number=case.case_number,
    )

    # Evaluate escalation rules
    actions = await ctx.bot.warning_repo.get_actions(ctx.guild.id)
    triggered_actions = [action for action in actions if prev_points < action.points <= new_points]

    escalated_action: WarningAction | None = None
    if triggered_actions:
        escalated_action = max(triggered_actions, key=lambda a: a.points)
        escalation_reason = f"Automated warning escalation ({new_points} points reached)"

        match escalated_action.action:
            case "timeout":
                duration_sec = escalated_action.duration_seconds or 3600
                timeout_delta = timedelta(seconds=duration_sec)
                with contextlib.suppress(discord.Forbidden, discord.HTTPException):
                    await member.timeout(timeout_delta, reason=escalation_reason)
                readable_duration = humanize.precisedelta(timeout_delta)
                await record_case(
                    ctx,
                    action="timeout",
                    target=member,
                    reason=f"{escalation_reason}: {readable_duration}",
                )
            case "kick":
                with contextlib.suppress(discord.Forbidden, discord.HTTPException):
                    await member.kick(reason=escalation_reason)
                await record_case(ctx, action="kick", target=member, reason=escalation_reason)
            case "ban":
                with contextlib.suppress(discord.Forbidden, discord.HTTPException):
                    await member.ban(reason=escalation_reason, delete_message_days=0)
                await record_case(ctx, action="ban", target=member, reason=escalation_reason)
            case "softban":
                with contextlib.suppress(discord.Forbidden, discord.HTTPException):
                    await member.ban(reason=escalation_reason, delete_message_days=1)
                    await ctx.guild.unban(
                        discord.Object(id=member.id),
                        reason="Automated softban purge",
                    )
                await record_case(ctx, action="softban", target=member, reason=escalation_reason)

    # Direct message user regarding warning and escalation
    escalation_notice = ""
    if escalated_action:
        if escalated_action.action == "timeout":
            dur = humanize.precisedelta(
                timedelta(seconds=escalated_action.duration_seconds or 3600)
            )
            escalation_notice = (
                f"\nAn automated **{dur} timeout** was applied as you reached "
                f"{new_points} warning points."
            )
        else:
            escalation_notice = (
                f"\nAn automated **{escalated_action.action.upper()}** was applied as you "
                f"reached {new_points} warning points."
            )

    with contextlib.suppress(discord.Forbidden, discord.HTTPException):
        await member.send(
            f"You received a warning in **{ctx.guild.name}** by **{ctx.author}**!\n"
            f"Reason: {reason}\n"
            f"Points: +{resolved_points} (Total active points: {new_points})"
            f"{escalation_notice}"
        )

    return case, warning_record, new_points, escalated_action


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


async def softban_member(
    ctx: Context,
    member: discord.Member,
    days: int = 1,
    reason: str = "Not specified",
) -> ModCase:
    """Ban a user and immediately unban them to purge recent messages without permanent ban."""
    validate_target(ctx, member)
    clean_days = max(1, min(7, days))
    audit_reason = get_audit_reason(ctx.author, f"Softban ({clean_days}d purge): {reason}")

    with contextlib.suppress(discord.Forbidden, discord.HTTPException):
        await member.send(
            f"You were softbanned from **{ctx.guild.name}** by **{ctx.author}**!\nReason: {reason}"
        )

    await ctx.guild.ban(member, reason=audit_reason, delete_message_seconds=clean_days * 86400)
    await ctx.guild.unban(member, reason=f"Softban unban: {reason}")
    return await record_case(ctx, action="softban", target=member, reason=reason)


async def tempban_member(
    ctx: Context,
    member: discord.Member,
    duration: timedelta,
    reason: str = "Not specified",
) -> ModCase:
    """Temporarily ban a member and record the expiration in SQLite."""
    validate_target(ctx, member)
    unban_at = datetime.now(UTC) + duration
    duration_str = humanize.naturaldelta(duration)
    audit_reason = get_audit_reason(ctx.author, f"Tempban ({duration_str}): {reason}")

    with contextlib.suppress(discord.Forbidden, discord.HTTPException):
        await member.send(
            f"You were temporarily banned from **{ctx.guild.name}** for {duration_str}!\n"
            f"Reason: {reason}"
        )

    await member.ban(reason=audit_reason)
    await ctx.bot.tempban_repo.add_tempban(ctx.guild.id, member.id, unban_at, reason)
    case_reason = f"{reason} (Until {unban_at.strftime('%Y-%m-%d %H:%M UTC')})"
    return await record_case(ctx, action="tempban", target=member, reason=case_reason)


async def hackban_user(
    ctx: Context,
    user_id: int,
    reason: str = "Not specified",
) -> ModCase:
    """Pre-emptively ban a malicious user ID before they join the server."""
    if user_id == ctx.guild.owner_id:
        raise HierarchyError("You cannot ban the server owner.")
    if user_id == ctx.bot.user.id:
        raise HierarchyError("I cannot ban myself.")
    if user_id == ctx.author.id:
        raise HierarchyError("You cannot ban yourself.")

    member = ctx.guild.get_member(user_id)
    if member:
        validate_target(ctx, member)
        return await ban_member(ctx, member, reason)

    audit_reason = get_audit_reason(ctx.author, f"Pre-ban / Hackban: {reason}")
    target_obj = discord.Object(id=user_id)
    await ctx.guild.ban(target_obj, reason=audit_reason)

    user_obj: discord.User | discord.Object = target_obj
    with contextlib.suppress(discord.HTTPException):
        user_obj = await ctx.bot.fetch_user(user_id)

    return await record_case(ctx, action="hackban", target=user_obj, reason=reason)


async def unban_member(
    ctx: Context,
    user: discord.User,
    reinvite: bool = False,
    reason: str = "Not specified",
) -> tuple[ModCase, str | None]:
    """Unban a user and optionally generate and deliver a single-use reinvite link."""
    audit_reason = get_audit_reason(ctx.author, f"Unban: {reason}")
    await ctx.guild.unban(user, reason=audit_reason)
    await ctx.bot.tempban_repo.remove_tempban(ctx.guild.id, user.id)

    case = await record_case(ctx, action="unban", target=user, reason=reason)
    invite_url: str | None = None

    if reinvite and isinstance(ctx.channel, discord.TextChannel | discord.VoiceChannel):
        with contextlib.suppress(discord.Forbidden, discord.HTTPException):
            invite = await ctx.channel.create_invite(
                max_uses=1,
                max_age=86400,
                unique=True,
                reason=f"Unban reinvite for {user}",
            )
            invite_url = invite.url
            await user.send(
                f"You were unbanned from **{ctx.guild.name}** by **{ctx.author}**!\n"
                f"Here is a one-time invite link to rejoin: {invite.url}"
            )

    return case, invite_url


async def massban_users(
    ctx: Context,
    user_ids: list[int],
    reason: str = "Not specified",
) -> tuple[list[int], list[int]]:
    """Ban multiple user IDs in bulk and record infractions."""
    banned: list[int] = []
    failed: list[int] = []
    audit_reason = get_audit_reason(ctx.author, f"Massban: {reason}")

    for uid in user_ids:
        if uid in (ctx.guild.owner_id, ctx.bot.user.id, ctx.author.id):
            failed.append(uid)
            continue

        member = ctx.guild.get_member(uid)
        if member:
            try:
                validate_target(ctx, member)
            except Exception:
                failed.append(uid)
                continue

        try:
            target_obj = discord.Object(id=uid)
            await ctx.guild.ban(target_obj, reason=audit_reason)
            banned.append(uid)
            user_obj: discord.User | discord.Object = member or target_obj
            await record_case(ctx, action="massban", target=user_obj, reason=reason)
        except Exception:
            failed.append(uid)

    return banned, failed


async def purge_channel(
    channel: discord.TextChannel | discord.Thread | discord.VoiceChannel,
    amount: int,
) -> int:
    """Purge a specified number of messages from a channel."""
    purged = await channel.purge(limit=amount)
    return len(purged)
