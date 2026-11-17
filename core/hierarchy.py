"""Role hierarchy validation rules and permission checking functions."""

from __future__ import annotations

import discord
from discord.ext.commands import Context

from core.config import get_config
from core.exceptions import HierarchyError


def validate_hierarchy(ctx: Context, target: discord.Member) -> None:
    """Execute all role hierarchy rules against the target member.

    Raises:
        HierarchyError: If any hierarchy constraint is violated.
    """
    if not ctx.guild:
        return

    if target.id == ctx.guild.owner_id:
        raise HierarchyError("You cannot perform moderation actions against the server owner.")

    if target.id == ctx.bot.user.id:
        raise HierarchyError("I cannot perform moderation actions against myself.")

    if target.id == ctx.author.id:
        raise HierarchyError("You cannot perform moderation actions against yourself.")

    bot_config = getattr(ctx.bot, "config", None) or get_config()
    is_owner_invoker = bot_config.is_owner(ctx.author.id)
    is_guild_owner = ctx.author.id == ctx.guild.owner_id

    author_member = (
        ctx.author
        if isinstance(ctx.author, discord.Member)
        else ctx.guild.get_member(ctx.author.id)
    )
    author_top_role = getattr(author_member, "top_role", None)
    target_top_role = getattr(target, "top_role", None)

    if (
        not (is_owner_invoker or is_guild_owner)
        and author_top_role
        and target_top_role
        and author_top_role <= target_top_role
    ):
        raise HierarchyError(
            f"Your highest role ({author_top_role.mention}) must be strictly higher than "
            f"{target.mention}'s highest role ({target_top_role.mention})."
        )

    bot_member = ctx.guild.me or (ctx.bot.user and ctx.guild.get_member(ctx.bot.user.id))
    bot_top_role = getattr(bot_member, "top_role", None)
    if bot_top_role and target_top_role and bot_top_role <= target_top_role:
        raise HierarchyError(
            f"My highest role ({bot_top_role.mention}) must be strictly higher than "
            f"{target.mention}'s highest role ({target_top_role.mention}) to take action."
        )


def can_moderate(ctx: Context, target: discord.Member) -> tuple[bool, str | None]:
    """Check if the context author can moderate the target without raising."""
    try:
        validate_hierarchy(ctx, target)
        return True, None
    except HierarchyError as exc:
        return False, str(exc)
