"""Stores moderation commands of Bot"""

import discord
from discord.ext import commands
from discord.ext.commands import Context

from helpers import exceptions


class Moderation(commands.Cog, name="moderation"):
    """Moderation Commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: Context) -> bool:
        """Verify the moderation module is enabled for the invoking guild."""
        if not ctx.guild:
            return True
        if ctx.bot.config.is_owner(ctx.author.id) or ctx.author.guild_permissions.administrator:
            return True
        is_enabled = await ctx.bot.guild_repo.is_module_enabled(ctx.guild.id, "moderation")
        if not is_enabled:
            raise exceptions.ModuleDisabled("moderation")
        return True

    @commands.hybrid_command(
        name="say",
        aliases=["echo"],
        description="The bot will say anything you want",
    )
    @commands.guild_only()
    async def say(self, ctx: Context, *, sentence: str):
        """The bot will say anything you want."""
        await ctx.send(sentence)

    @commands.hybrid_command(
        name="embed",
        description="The bot will say anything you want in embeds",
    )
    @commands.guild_only()
    async def embed(self, ctx: Context, *, sentence: str):
        """The bot will say anything you want in embeds."""
        embed = discord.Embed(
            description=sentence,
            color=0x42F56C,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="warn",
        description="Warns a user in their private messages",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def warn(
        self,
        ctx: Context,
        member: discord.Member,
        *,
        reason: str = "Not specified",
    ):
        """Warns a user in their private messages."""
        embed = discord.Embed(
            title="User Warned!",
            description=f"**{member}** was warned by **{ctx.author}**!",
            color=0x42F56C,
        )
        embed.add_field(name="Reason:", value=reason)
        await ctx.send(embed=embed)
        try:
            await member.send(f"You were warned by **{ctx.author}**!\nReason: {reason}")
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def kick_ban_common(
        self,
        ctx: Context,
        member: discord.Member,
        action: str,
        reason: str,
    ):
        """Common logic for kick and ban commands."""
        try:
            if member.guild_permissions.administrator:
                raise commands.CheckFailure("User has Admin permissions.")

            try:
                await member.send(
                    f"You were {action}ned from **{ctx.guild.name}** by **{ctx.author}**!\n"
                    f"Reason: {reason}"
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

            if action == "kick":
                await member.kick(reason=reason)
            elif action == "ban":
                await member.ban(reason=reason)

            embed = discord.Embed(
                title=f"User {action.capitalize()}!",
                description=f"**{member}** was {action}ned by **{ctx.author}**!",
                color=0x42F56C,
            )
            embed.add_field(name="Reason:", value=reason)
            await ctx.send(embed=embed)

        except commands.CheckFailure as e:
            embed = discord.Embed(title="Error!", description=str(e), color=0xE02B2B)
            await ctx.send(embed=embed)
        except discord.Forbidden:
            embed = discord.Embed(
                title="Error!",
                description=(
                    f"An error occurred while trying to {action} the user. "
                    f"Make sure my role is above the role of the user you want to {action}."
                ),
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="kick", description="Kick a user out of the server")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    async def kick(
        self,
        ctx: Context,
        member: discord.Member,
        *,
        reason: str = "Not specified",
    ):
        """Kick a user out of the server."""
        await self.kick_ban_common(ctx, member, "kick", reason)

    @commands.hybrid_command(name="ban", description="Ban a user from the server")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def ban(
        self,
        ctx: Context,
        member: discord.Member,
        *,
        reason: str = "Not specified",
    ):
        """Ban a user from the server."""
        await self.kick_ban_common(ctx, member, "ban", reason)

    @commands.hybrid_command(name="purge", description="Delete a number of messages")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True, manage_channels=True)
    async def purge(self, ctx: Context, amount: int):
        """Delete a number of messages."""
        if amount < 1:
            embed = discord.Embed(
                title="Error!",
                description=f"`{amount}` is not a valid number. Must be at least 1.",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)
            return

        purged_messages = await ctx.channel.purge(limit=amount)
        embed = discord.Embed(
            title="Chat Cleared!",
            description=(f"**{ctx.author}** cleared **{len(purged_messages)}** messages!"),
            color=0x42F56C,
        )
        await ctx.send(embed=embed, delete_after=5)


async def setup(bot: commands.Bot):
    """Add Moderation commands to cogs"""
    await bot.add_cog(Moderation(bot))
