"""Domain service handling business logic and execution for moderation actions."""

import contextlib

import discord
from discord.ext.commands import Context

from helpers.checks import get_audit_reason
from helpers.hierarchy import HierarchyValidator


class ModerationService:
    """Service layer orchestrating discipline, hierarchy validation, and audit attribution."""

    @staticmethod
    def validate_target(ctx: Context, member: discord.Member) -> None:
        """Enforce role hierarchy and protection rules against target member."""
        HierarchyValidator.validate(ctx, member)

    @classmethod
    async def warn_member(
        cls,
        ctx: Context,
        member: discord.Member,
        reason: str,
    ) -> None:
        """Validate hierarchy and deliver warning DM to target member."""
        cls.validate_target(ctx, member)
        with contextlib.suppress(discord.Forbidden, discord.HTTPException):
            await member.send(
                f"You were warned in **{ctx.guild.name}** by **{ctx.author}**!\nReason: {reason}"
            )

    @classmethod
    async def kick_member(
        cls,
        ctx: Context,
        member: discord.Member,
        reason: str,
    ) -> None:
        """Validate hierarchy, notify member, and perform guild kick with audit attribution."""
        cls.validate_target(ctx, member)
        audit_reason = get_audit_reason(ctx.author, reason)

        with contextlib.suppress(discord.Forbidden, discord.HTTPException):
            await member.send(
                f"You were kicked from **{ctx.guild.name}** by **{ctx.author}**!\nReason: {reason}"
            )

        await member.kick(reason=audit_reason)

    @classmethod
    async def ban_member(
        cls,
        ctx: Context,
        member: discord.Member,
        reason: str,
    ) -> None:
        """Validate hierarchy, notify member, and perform guild ban with audit attribution."""
        cls.validate_target(ctx, member)
        audit_reason = get_audit_reason(ctx.author, reason)

        with contextlib.suppress(discord.Forbidden, discord.HTTPException):
            await member.send(
                f"You were banned from **{ctx.guild.name}** by **{ctx.author}**!\nReason: {reason}"
            )

        await member.ban(reason=audit_reason)

    @staticmethod
    async def purge_channel(
        channel: discord.TextChannel | discord.Thread | discord.VoiceChannel,
        amount: int,
    ) -> int:
        """Purge a specified number of messages from a channel."""
        purged = await channel.purge(limit=amount)
        return len(purged)
