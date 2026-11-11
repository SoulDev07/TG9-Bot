"""Stores fun commands of Bot"""

from __future__ import annotations

import random

import discord
from discord.ext import commands
from discord.ext.commands import Context

from helpers import exceptions
from helpers.embeds import EmbedColor, make_embed
from views.games import RockPaperScissorsView

EMBED_COLORS = {
    "default": EmbedColor.WARNING,
    "win": EmbedColor.SUCCESS,
    "draw": EmbedColor.WARNING,
    "lose": EmbedColor.ERROR,
}


class Fun(commands.Cog, name="fun"):
    """Fun Commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: Context) -> bool:
        """Verify the fun module is enabled for the invoking guild."""
        if not ctx.guild:
            return True
        if ctx.bot.config.is_owner(ctx.author.id) or ctx.author.guild_permissions.administrator:
            return True
        is_enabled = await ctx.bot.guild_repo.is_module_enabled(ctx.guild.id, "fun")
        if not is_enabled:
            raise exceptions.ModuleDisabled("fun")
        return True

    def get_embed(
        self,
        ctx: Context,
        title: str,
        desc: str = "",
        color: int = EmbedColor.WARNING,
    ) -> discord.Embed:
        return make_embed(
            title=title,
            description=desc,
            color=color,
            author_name=ctx.author.display_name,
            author_icon=ctx.author.display_avatar.url,
        )

    @commands.hybrid_command(name="coinflip", description="Flip a coin")
    async def coinflip(self, ctx: Context):
        """Flip a coin"""
        result = random.choice(["Heads", "Tails"])
        result_embed = self.get_embed(
            ctx,
            title="Coinflip",
            desc=f"The coin landed on: **{result}**",
            color=EMBED_COLORS["default"],
        )
        await ctx.send(embed=result_embed)

    @commands.hybrid_command(
        name="rps",
        aliases=["rockpaperscissors"],
        description="Play interactive Rock, Paper, Scissors with buttons",
    )
    async def rock_paper_scissors(self, ctx: Context):
        """Play interactive Rock, Paper, Scissors with buttons."""
        view = RockPaperScissorsView(invoker=ctx.author)
        embed = self.get_embed(
            ctx,
            title="Rock, Paper, Scissors!",
            desc="Choose your move below by clicking a button:",
            color=EMBED_COLORS["default"],
        )
        message = await ctx.send(embed=embed, view=view)
        view.message = message


async def setup(bot: commands.Bot):
    """Add Fun commands to cogs"""
    await bot.add_cog(Fun(bot))
