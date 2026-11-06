"""Role hierarchy validation rules and validator engine."""

import discord
from discord.ext.commands import Context

from helpers.config import get_config
from helpers.exceptions import HierarchyError


class HierarchyValidator:
    """Enforces Discord role hierarchy and protective rules before moderation actions."""

    @staticmethod
    def validate(ctx: Context, target: discord.Member) -> None:
        """Execute all hierarchy rules against the target member.

        Raises:
            HierarchyError: If any hierarchy constraint is violated.
        """
        if not ctx.guild:
            return

        # Rule 1: Cannot target the guild owner
        if target.id == ctx.guild.owner_id:
            raise HierarchyError("You cannot perform moderation actions against the server owner.")

        # Rule 2: Cannot target the bot itself
        if target.id == ctx.bot.user.id:
            raise HierarchyError("I cannot perform moderation actions against myself.")

        # Rule 3: Cannot target yourself
        if target.id == ctx.author.id:
            raise HierarchyError("You cannot perform moderation actions against yourself.")

        bot_config = getattr(ctx.bot, "config", None) or get_config()
        is_owner_invoker = bot_config.is_owner(ctx.author.id)
        is_guild_owner = ctx.author.id == ctx.guild.owner_id

        # Rule 4: Moderator must outrank target (bypassed by bot owner or guild owner)
        if not (is_owner_invoker or is_guild_owner) and ctx.author.top_role <= target.top_role:
            raise HierarchyError(
                f"Your highest role ({ctx.author.top_role.mention}) must be strictly higher than "
                f"{target.mention}'s highest role ({target.top_role.mention})."
            )

        # Rule 5: Bot's highest role must outrank target
        bot_member = ctx.guild.me
        if bot_member.top_role <= target.top_role:
            raise HierarchyError(
                f"My highest role ({bot_member.top_role.mention}) must be strictly higher than "
                f"{target.mention}'s highest role ({target.top_role.mention}) to take action."
            )
