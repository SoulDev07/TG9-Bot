"""Stores fun commands of Bot"""

from __future__ import annotations

import random

import discord
from discord.ext import commands
from discord.ext.commands import Context

from core import exceptions
from core.embeds import EmbedColor, error_embed, make_embed
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

    @commands.hybrid_command(
        name="coinflip",
        aliases=["flip", "coin"],
        description="Flip a coin",
    )
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

    @commands.hybrid_command(
        name="roll",
        aliases=["dice"],
        description="Roll dice with configurable sides and count",
    )
    @discord.app_commands.describe(
        sides="Number of sides per die (default: 6, max: 1000)",
        count="Number of dice to roll (default: 1, max: 20)",
    )
    async def roll(self, ctx: Context, sides: int = 6, count: int = 1):
        """Roll dice with configurable sides and count."""
        if count < 1 or count > 20:
            await ctx.send(
                embed=error_embed(description="Dice count must be between 1 and 20."),
                ephemeral=True,
            )
            return

        if sides < 2 or sides > 1000:
            await ctx.send(
                embed=error_embed(description="Sides per die must be between 2 and 1,000."),
                ephemeral=True,
            )
            return

        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls)

        if count == 1:
            desc = f"🎲 You rolled a **{rolls[0]}** (1d{sides})!"
        else:
            rolls_str = ", ".join(str(r) for r in rolls)
            desc = f"🎲 Rolls: `{rolls_str}`\n**Total:** **{total}** ({count}d{sides})"

        embed = self.get_embed(ctx, title="Dice Roll", desc=desc, color=EMBED_COLORS["default"])
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="8ball",
        aliases=["eightball", "ball"],
        description="Ask the magic 8-ball a question",
    )
    @discord.app_commands.describe(question="The question to ask the magic 8-ball")
    async def eight_ball(self, ctx: Context, *, question: str):
        """Ask the magic 8-ball a question."""
        answers = [
            "It is certain.",
            "It is decidedly so.",
            "Without a doubt.",
            "Yes definitely.",
            "You may rely on it.",
            "As I see it, yes.",
            "Most likely.",
            "Outlook good.",
            "Yes.",
            "Signs point to yes.",
            "Reply hazy, try again.",
            "Ask again later.",
            "Better not tell you now.",
            "Cannot predict now.",
            "Concentrate and ask again.",
            "Don't count on it.",
            "My reply is no.",
            "My sources say no.",
            "Outlook not so good.",
            "Very doubtful.",
        ]
        answer = random.choice(answers)
        embed = self.get_embed(
            ctx,
            title="🎱 Magic 8-Ball",
            desc=f"**Question:** {question}\n**Answer:** {answer}",
            color=EMBED_COLORS["default"],
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    """Add Fun commands to cogs"""
    await bot.add_cog(Fun(bot))
