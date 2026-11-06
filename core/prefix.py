"""Dynamic command prefix resolution strategies."""

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from bot import DiscordBot


class DynamicPrefixResolver:
    """Strategy for resolving command prefixes based on guild settings and fallbacks."""

    @staticmethod
    async def resolve(bot: "DiscordBot", message: discord.Message) -> list[str]:
        """Dynamically resolve command prefixes per guild with fallback to default."""
        default_prefix = bot.config.bot_prefix
        if not message.guild:
            return commands.when_mentioned_or(default_prefix)(bot, message)

        prefix = await bot.guild_repo.get_prefix(message.guild.id, default=default_prefix)
        return commands.when_mentioned_or(prefix)(bot, message)
