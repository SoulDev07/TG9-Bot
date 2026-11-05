"""Stores general commands of Bot"""

import platform
import time
from datetime import UTC, datetime

import discord
import humanize
from discord.ext import commands
from discord.ext.commands import Context

BOT_VERSION = "2.0.0"


class General(commands.Cog, name="general"):
    """General Commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="info",
        aliases=["botinfo", "stats"],
        description="Get bot information, status, and uptime",
    )
    async def info(self, ctx: Context):
        """Get information and runtime statistics about the Bot."""
        now = datetime.now(UTC)
        start_time = getattr(self.bot, "start_time", now)
        uptime = humanize.naturaldelta(now - start_time)

        guilds_count = len(self.bot.guilds)
        total_members = sum(guild.member_count or 0 for guild in self.bot.guilds)

        if ctx.guild:
            prefix = await self.bot.guild_repo.get_prefix(
                ctx.guild.id, default=getattr(self.bot.config, "bot_prefix", "Tg9 ")
            )
        else:
            prefix = getattr(self.bot.config, "bot_prefix", "Tg9 ")

        embed = discord.Embed(
            title="TG9 Bot — Status & Information",
            description="A modern, general-purpose Discord bot.",
            color=0x42F56C,
        )
        embed.set_author(
            name=self.bot.user.name if self.bot.user else "TG9",
            icon_url=self.bot.user.display_avatar.url if self.bot.user else None,
        )
        embed.add_field(name="Bot Version", value=f"`{BOT_VERSION}`", inline=True)
        embed.add_field(name="discord.py", value=f"`v{discord.__version__}`", inline=True)
        embed.add_field(name="Python", value=f"`v{platform.python_version()}`", inline=True)
        embed.add_field(name="Prefix", value=f"`{prefix}`", inline=True)
        embed.add_field(name="Servers", value=f"`{guilds_count}`", inline=True)
        embed.add_field(name="Users Cached", value=f"`{total_members}`", inline=True)
        embed.add_field(name="Uptime", value=uptime, inline=True)
        embed.add_field(
            name="Gateway Latency", value=f"`{round(self.bot.latency * 1000)}ms`", inline=True
        )

        embed.set_footer(text=f"Requested by {ctx.author}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="ping", description="Check bot latency and gateway responsiveness"
    )
    async def ping(self, ctx: Context):
        """Check the bot's gateway latency and message roundtrip speed."""
        gateway_ms = round(self.bot.latency * 1000)

        start_time = time.perf_counter()
        initial_embed = discord.Embed(
            title="🏓 Pong!",
            description="Measuring API roundtrip...",
            color=0x42F56C,
        )
        message = await ctx.send(embed=initial_embed)
        end_time = time.perf_counter()

        roundtrip_ms = round((end_time - start_time) * 1000)

        result_embed = discord.Embed(
            title="🏓 Pong!",
            color=0x42F56C,
        )
        result_embed.add_field(name="Gateway Latency", value=f"`{gateway_ms}ms`", inline=True)
        result_embed.add_field(name="API Roundtrip", value=f"`{roundtrip_ms}ms`", inline=True)
        await message.edit(embed=result_embed)

    @commands.hybrid_command(
        name="prefix",
        description="View or set the custom command prefix for this server",
    )
    @commands.guild_only()
    async def prefix(self, ctx: Context, *, new_prefix: str | None = None):
        """View or configure the server command prefix."""
        settings = await self.bot.guild_repo.get_or_create(
            ctx.guild.id,
            default_prefix=self.bot.config.bot_prefix,
        )

        if new_prefix is None:
            embed = discord.Embed(
                title="Server Prefix",
                description=f"Current prefix for **{ctx.guild.name}** is `{settings.prefix}`",
                color=0x42F56C,
            )
            await ctx.send(embed=embed)
            return

        is_owner = self.bot.config.is_owner(ctx.author.id)
        is_guild_owner = ctx.author.id == ctx.guild.owner_id
        has_manage_guild = ctx.author.guild_permissions.manage_guild
        has_admin_role = await self.bot.guild_repo.has_role_type(ctx.author, "admin")
        if not (is_owner or is_guild_owner or has_manage_guild or has_admin_role):
            embed = discord.Embed(
                title="Permission Denied",
                description=(
                    "You need `Manage Server` permission or an Administrator role "
                    "to change the bot prefix."
                ),
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)
            return

        clean_prefix = new_prefix.strip()
        if not clean_prefix or len(clean_prefix) > 10:
            embed = discord.Embed(
                title="Invalid Prefix",
                description="Prefix length must be between 1 and 10 characters.",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)
            return

        await self.bot.guild_repo.update_prefix(ctx.guild.id, clean_prefix)
        embed = discord.Embed(
            title="Prefix Updated",
            description=f"The command prefix for **{ctx.guild.name}** is now `{clean_prefix}`.",
            color=0x42F56C,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="server",
        aliases=["support", "supportserver"],
        description="Get support server invite link",
    )
    async def server(self, ctx: Context):
        """Get the invite link for the bot's support server."""
        server_link = getattr(self.bot.config, "bot_invite_link", "")
        if not server_link:
            await ctx.send("Support server invite link is currently not configured.")
            return

        embed = discord.Embed(
            description=f"Join the support server by clicking [here]({server_link}).",
            color=0xD75BF4,
        )
        try:
            await ctx.author.send(embed=embed)
            await ctx.send("I sent you a private message!")
        except discord.Forbidden:
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="poll", description="Generate an interactive poll")
    @commands.guild_only()
    async def poll(self, ctx: Context, *, title: str):
        """Create a poll where members can vote."""
        embed = discord.Embed(
            title="A new poll has been created!",
            description=f"{title}",
            color=0x42F56C,
        )
        embed.set_footer(text=f"Poll created by: {ctx.author} • React to vote!")
        embed_message = await ctx.send(embed=embed)
        await embed_message.add_reaction("👍")
        await embed_message.add_reaction("👎")
        await embed_message.add_reaction("🤷")


async def setup(bot: commands.Bot):
    """Add General commands to cogs"""
    await bot.add_cog(General(bot))
