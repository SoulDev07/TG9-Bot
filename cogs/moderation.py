"""Stores moderation commands of Bot"""

import discord
from discord.ext import commands
from discord.ext.commands import Context


class Moderation(commands.Cog, name="moderation"):
    """Moderation Commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="say", aliases=["echo"], description="The bot will say anything you want")
    @commands.guild_only()
    async def say(self, ctx: Context, sentence: str):
        """The bot will say anything you want."""

        await ctx.send(sentence)

    @commands.hybrid_command(name="embed", description="The bot will say anything you want in embeds")
    @commands.guild_only()
    async def embed(self, ctx: Context, sentence: str):
        """The bot will say anything you want in embeds."""

        embed = discord.Embed(
            description=sentence,
            color=0x42F56C
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="warn", description="Warns a user in his private messages")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx: Context, member: discord.Member, *, reason: str = "Not specified"):
        """Warns a user in his private messages."""

        embed = discord.Embed(
            title="User Warned!",
            description=f"**{member}** was warned by **{ctx.author}**!",
            color=0x42F56C
        )
        embed.add_field(name="Reason:", value=reason)
        await ctx.send(embed=embed)
        try:
            await member.send(f"You were warned by **{ctx.author}**!\nReason: {reason}")
        except:
            pass

    async def kick_ban_common(self, ctx: Context, member: discord.Member, action: str, reason: str):
        """Common logic for kick and ban commands."""
        try:
            if member.guild_permissions.administrator:
                raise commands.CheckFailure("User has Admin permissions.")

            if action == "kick":
                await member.kick(reason=reason)
            elif action == "ban":
                await member.ban(reason=reason)

            embed = discord.Embed(
                title=f"User {action.capitalize()}!",
                description=f"**{member}** was {action}ned by **{ctx.author}**!",
                color=0x42F56C
            )
            embed.add_field(name="Reason:", value=reason)
            await ctx.send(embed=embed)
            await member.send(f"You were {action}ned by **{ctx.author}**!\nReason: {reason}")

        except commands.CheckFailure as e:
            embed = discord.Embed(title="Error!", description=str(e), color=0xE02B2B)
            await ctx.send(embed=embed)
        except discord.Forbidden:
            embed = discord.Embed(
                title="Error!",
                description=f"An error occurred while trying to {action} the user. "
                f"Make sure my role is above the role of the user you want to {action}.",
                color=0xE02B2B
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name='kick', description="Kick a user out of the server")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: Context, member: discord.Member, reason: str = "Not specified"):
        """Kick a user out of the server."""
        await self.kick_ban_common(ctx, member, "kick", reason)

    @commands.hybrid_command(name="ban", description="Ban a user from the server")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: Context, member: discord.Member, reason: str = "Not specified"):
        """Ban a user from the server."""
        await self.kick_ban_common(ctx, member, "ban", reason)

    @commands.hybrid_command(name="purge", description="Delete a number of messages")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True, manage_channels=True)
    async def purge(self, ctx: Context, amount):
        """Delete a number of messages."""

        try:
            amount = int(amount)
        except ValueError:
            embed = discord.Embed(
                title="Error!",
                description=f"`{amount}` is not a valid number.",
                color=0xE02B2B
            )
            await ctx.send(embed=embed)
            return

        if amount < 1:
            embed = discord.Embed(
                title="Error!",
                description=f"`{amount}` is not a valid number.",
                color=0xE02B2B
            )
            await ctx.send(embed=embed)
            return

        purged_messages = await ctx.channel.purge(limit=amount)
        embed = discord.Embed(
            title="Chat Cleared!",
            description=(f"**{ctx.author}** cleared "
                         f"**{len(purged_messages)}** messages!"),
            color=0x42F56C
        )
        await ctx.send(embed=embed, delete_after=5)


async def setup(bot: commands.Bot):
    """Add Moderation commands to cogs"""
    await bot.add_cog(Moderation(bot))
