"""Stores general commands of Bot"""

from __future__ import annotations

import platform
import time
from datetime import UTC, datetime

import discord
import humanize
from discord.ext import commands
from discord.ext.commands import Context

from core.embeds import error_embed, make_embed, success_embed
from views.poll import PollView

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
                ctx.guild.id, default=self.bot.config.prefix
            )
        else:
            prefix = self.bot.config.prefix

        embed = make_embed(
            title="TG9 Bot: Status & Information",
            description="A modern, general-purpose Discord bot.",
            author_name=self.bot.user.name if self.bot.user else "TG9",
            author_icon=self.bot.user.display_avatar.url if self.bot.user else None,
            fields=[
                ("Bot Version", f"`{BOT_VERSION}`", True),
                ("discord.py", f"`v{discord.__version__}`", True),
                ("Python", f"`v{platform.python_version()}`", True),
                ("Prefix", f"`{prefix}`", True),
                ("Servers", f"`{guilds_count}`", True),
                ("Users Cached", f"`{total_members}`", True),
                ("Uptime", uptime, True),
                ("Gateway Latency", f"`{round(self.bot.latency * 1000)}ms`", True),
            ],
            footer=f"Requested by {ctx.author}",
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="ping",
        aliases=["latency"],
        description="Check bot latency and gateway responsiveness",
    )
    async def ping(self, ctx: Context):
        """Check the bot's gateway latency and message roundtrip speed."""
        gateway_ms = round(self.bot.latency * 1000)

        start_time = time.perf_counter()
        initial_embed = success_embed(
            title="🏓 Pong!",
            description="Measuring API roundtrip...",
        )
        message = await ctx.send(embed=initial_embed)
        end_time = time.perf_counter()

        roundtrip_ms = round((end_time - start_time) * 1000)

        result_embed = success_embed(
            title="🏓 Pong!",
            fields=[
                ("Gateway Latency", f"`{gateway_ms}ms`", True),
                ("API Roundtrip", f"`{roundtrip_ms}ms`", True),
            ],
        )
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
            default_prefix=self.bot.config.prefix,
        )

        if new_prefix is None:
            embed = success_embed(
                title="Server Prefix",
                description=f"Current prefix for **{ctx.guild.name}** is `{settings.prefix}`",
            )
            await ctx.send(embed=embed)
            return

        is_owner = self.bot.config.is_owner(ctx.author.id)
        is_guild_owner = ctx.author.id == ctx.guild.owner_id
        has_manage_guild = ctx.author.guild_permissions.manage_guild
        has_admin_role = await self.bot.guild_repo.has_role_type(ctx.author, "admin")
        if not (is_owner or is_guild_owner or has_manage_guild or has_admin_role):
            embed = error_embed(
                title="Permission Denied",
                description=(
                    "You need `Manage Server` permission or an Administrator role "
                    "to change the bot prefix."
                ),
            )
            await ctx.send(embed=embed)
            return

        clean_prefix = new_prefix.strip()
        if not clean_prefix or len(clean_prefix) > 10:
            embed = error_embed(
                title="Invalid Prefix",
                description="Prefix length must be between 1 and 10 characters.",
            )
            await ctx.send(embed=embed)
            return

        await self.bot.guild_repo.update_prefix(ctx.guild.id, clean_prefix)
        embed = success_embed(
            title="Prefix Updated",
            description=f"The command prefix for **{ctx.guild.name}** is now `{clean_prefix}`.",
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="server",
        aliases=["support"],
        description="Get support server invite link",
    )
    async def server(self, ctx: Context):
        """Get the invite link for the bot's support server."""
        server_link = self.bot.config.invite_link
        if not server_link:
            await ctx.send("Support server invite link is currently not configured.")
            return

        embed = make_embed(
            description=f"Join the support server by clicking [here]({server_link}).",
            color=0xD75BF4,
        )
        try:
            await ctx.author.send(embed=embed)
            await ctx.send("I sent you a private message!")
        except discord.Forbidden:
            await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="poll",
        description="Generate an interactive button-based voting poll",
    )
    @discord.app_commands.describe(question="The question or topic for members to vote on")
    @commands.guild_only()
    async def poll(self, ctx: Context, *, question: str):
        """Create an interactive button-based poll with live vote tallies."""
        view = PollView(question=question, creator=ctx.author)
        embed = view.build_embed()
        message = await ctx.send(embed=embed, view=view)
        view.message = message

    @commands.hybrid_command(
        name="userinfo",
        aliases=["user", "whois"],
        description="Get detailed user profile and member information",
    )
    @discord.app_commands.describe(member="The user or member to inspect (defaults to you)")
    async def userinfo(self, ctx: Context, member: discord.Member | discord.User | None = None):
        """Get detailed profile and membership information about a user."""
        target = member or ctx.author
        created_ts = int(target.created_at.timestamp())

        fields = [
            ("Username", str(target), True),
            ("User ID", f"`{target.id}`", True),
            ("Account Created", f"<t:{created_ts}:R>\n(<t:{created_ts}:f>)", True),
        ]

        if isinstance(target, discord.Member):
            if target.joined_at:
                joined_ts = int(target.joined_at.timestamp())
                fields.append(("Joined Server", f"<t:{joined_ts}:R>\n(<t:{joined_ts}:f>)", True))

            if target.premium_since:
                boost_ts = int(target.premium_since.timestamp())
                fields.append(("Boosting Since", f"<t:{boost_ts}:R>", True))

            roles = [r.mention for r in reversed(target.roles) if not r.is_default()]
            roles_str = ", ".join(roles[:15]) if roles else "None"
            if len(roles) > 15:
                roles_str += f" *(and {len(roles) - 15} more)*"
            fields.append((f"Roles ({len(roles)})", roles_str, False))

            key_perms = []
            perms = target.guild_permissions
            if perms.administrator:
                key_perms.append("Administrator")
            if perms.manage_guild:
                key_perms.append("Manage Server")
            if perms.manage_roles:
                key_perms.append("Manage Roles")
            if perms.manage_channels:
                key_perms.append("Manage Channels")
            if perms.ban_members:
                key_perms.append("Ban Members")
            if perms.kick_members:
                key_perms.append("Kick Members")
            if perms.moderate_members:
                key_perms.append("Moderate Members")
            if perms.manage_messages:
                key_perms.append("Manage Messages")
            if key_perms:
                fields.append(("Key Permissions", ", ".join(key_perms), False))

        embed = make_embed(
            title=f"User Info: {target.display_name}",
            fields=fields,
            footer=f"Requested by {ctx.author}",
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="serverinfo",
        aliases=["guildinfo", "guild"],
        description="Get detailed statistics and metrics about this server",
    )
    @commands.guild_only()
    async def serverinfo(self, ctx: Context):
        """Get detailed statistics and metrics about the current server."""
        guild = ctx.guild
        created_ts = int(guild.created_at.timestamp())

        total_members = guild.member_count or 0
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        roles_count = len(guild.roles) - 1

        fields = [
            ("Owner", guild.owner.mention if guild.owner else f"`{guild.owner_id}`", True),
            ("Server ID", f"`{guild.id}`", True),
            ("Created", f"<t:{created_ts}:R>", True),
            ("Members", f"**{total_members}** total", True),
            (
                "Channels",
                f"💬 {text_channels} text • 🔊 {voice_channels} voice • 📁 {categories} categories",
                True,
            ),
            ("Roles", f"`{roles_count}` roles", True),
            (
                "Boost Status",
                f"Tier **{guild.premium_tier}** ({guild.premium_subscription_count or 0} boosts)",
                True,
            ),
            ("Verification Level", str(guild.verification_level).capitalize(), True),
        ]

        embed = make_embed(
            title=f"Server Info: {guild.name}",
            fields=fields,
            footer=f"Requested by {ctx.author}",
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        if guild.banner:
            embed.set_image(url=guild.banner.url)

        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="avatar",
        aliases=["av", "pfp"],
        description="Display full resolution avatar for a user",
    )
    @discord.app_commands.describe(user="The user whose avatar to view (defaults to you)")
    async def avatar(self, ctx: Context, user: discord.User | discord.Member | None = None):
        """Display full resolution avatar for a user."""
        target = user or ctx.author
        avatar_url = target.display_avatar.url

        embed = make_embed(
            title=f"Avatar: {target.display_name}",
            description=f"[Click here to open in browser]({avatar_url})",
        )
        embed.set_image(url=avatar_url)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    """Add General commands to cogs"""
    await bot.add_cog(General(bot))
