"""Help command for TG9 Bot."""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands
from discord.ext.commands import Context

from views.help import HelpMenuView

if TYPE_CHECKING:
    from bot import DiscordBot


class Help(commands.Cog, name="help"):
    """Help Commands"""

    def __init__(self, bot: DiscordBot):
        self.bot = bot

    @commands.hybrid_command(
        name="help",
        description="Browse command categories and syntax with an interactive dropdown",
    )
    async def help(self, ctx: Context):
        """Browse commands across all categories with an interactive menu."""
        view = HelpMenuView(bot=self.bot, invoker_id=ctx.author.id)
        embed = view.build_home_embed()
        await ctx.send(embed=embed, view=view)


async def setup(bot: DiscordBot):
    """Register Help cog."""
    await bot.add_cog(Help(bot))
