"""Stores fun commands of Bot"""

import contextlib
import random

import discord
from discord.ext import commands
from discord.ext.commands import Context

from helpers import exceptions
from helpers.embeds import EmbedColor, EmbedFactory

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
        return EmbedFactory.create(
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

    @commands.hybrid_command(name="rps", description="Play Rock, Paper, Scissors")
    async def rock_paper_scissors(self, ctx: Context):
        """Play Rock, Paper, Scissors"""
        reactions = {"🪨": 0, "🧻": 1, "✂": 2}
        embed = self.get_embed(ctx, "Please Choose")
        choose_msg = await ctx.send(embed=embed)

        for emoji in reactions:
            await choose_msg.add_reaction(emoji)

        def check(reaction, user):
            return user == ctx.author and str(reaction) in reactions

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=10, check=check)
            if not user:
                return

            user_choice_emote = reaction.emoji
            user_choice_index = reactions[user_choice_emote]

            bot_choice_emote = random.choice(list(reactions.keys()))
            bot_choice_index = reactions[bot_choice_emote]

            result_embed = self.get_embed(ctx, "", color=EMBED_COLORS["draw"])
            await choose_msg.clear_reactions()

            if user_choice_index == bot_choice_index:
                result_embed.description = f"**It's a draw!**\nWe both choose {user_choice_emote}."
            elif (user_choice_index - bot_choice_index) % 3 == 1:
                result_embed.description = (
                    f"**You win!**\nYour choice was {user_choice_emote}\n"
                    f"My choice was {bot_choice_emote}."
                )
                result_embed.colour = EMBED_COLORS["win"]
            else:
                result_embed.description = (
                    f"**I win!**\nYour choice was {user_choice_emote}\n"
                    f"My choice was {bot_choice_emote}."
                )
                result_embed.colour = EMBED_COLORS["lose"]
                await choose_msg.add_reaction("🇱")

            await choose_msg.edit(embed=result_embed)

        except TimeoutError:
            with contextlib.suppress(discord.HTTPException):
                await choose_msg.clear_reactions()
            timeout_embed = self.get_embed(
                ctx,
                title="Too late",
                color=EMBED_COLORS["lose"],
            )
            await choose_msg.edit(embed=timeout_embed)


async def setup(bot: commands.Bot):
    """Add Fun commands to cogs"""
    await bot.add_cog(Fun(bot))
