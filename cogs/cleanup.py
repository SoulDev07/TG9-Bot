"""Comprehensive message cleanup and purge suite."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from discord.ext.commands import Context

from core import checks, exceptions
from core.embeds import error_embed, success_embed
from core.logger import get_logger
from services.cleanup import (
    purge_bot_messages,
    purge_channel,
    purge_containing_text,
    purge_embed_messages,
    purge_file_messages,
    purge_messages_after,
    purge_user_messages,
)

if TYPE_CHECKING:
    from bot import DiscordBot

logger = get_logger()


class Cleanup(commands.Cog, name="cleanup"):
    """Message Cleanup & Purge Commands"""

    def __init__(self, bot: DiscordBot):
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

    @commands.hybrid_group(
        name="purge",
        aliases=["clear", "clean"],
        description="Comprehensive message cleanup and purge suite",
        invoke_without_command=True,
    )
    @discord.app_commands.describe(amount="Number of recent messages to purge (default: 10)")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def purge(self, ctx: Context, amount: int = 10):
        """Clean up recent messages in the current channel."""
        if ctx.invoked_subcommand is None:
            if amount < 1:
                await ctx.send(
                    embed=error_embed(description="Purge amount must be at least 1 message."),
                    ephemeral=True,
                )
                return

            if ctx.interaction is None:
                with contextlib.suppress(discord.NotFound, discord.Forbidden):
                    await ctx.message.delete()

            count = await purge_channel(
                ctx.channel,
                amount=min(amount, 1000),
                reason=f"Purge requested by {ctx.author}",
            )
            embed = success_embed(
                title="Chat Cleared",
                description=f"**{ctx.author}** cleared **{count}** messages.",
            )
            await ctx.send(embed=embed, delete_after=5)

    @purge.command(
        name="messages",
        description="Delete a specified number of recent messages",
    )
    @discord.app_commands.describe(amount="Number of recent messages to purge (1 to 1000)")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def purge_messages_cmd(self, ctx: Context, amount: int = 10):
        """Delete a specified number of recent messages."""
        if amount < 1:
            await ctx.send(
                embed=error_embed(description="Purge amount must be at least 1 message."),
                ephemeral=True,
            )
            return

        if ctx.interaction is None:
            with contextlib.suppress(discord.NotFound, discord.Forbidden):
                await ctx.message.delete()

        count = await purge_channel(
            ctx.channel,
            amount=min(amount, 1000),
            reason=f"Purge messages requested by {ctx.author}",
        )
        embed = success_embed(
            title="Chat Cleared",
            description=f"**{ctx.author}** cleared **{count}** messages.",
        )
        await ctx.send(embed=embed, delete_after=5)

    @purge.command(
        name="user",
        description="Delete messages strictly from a targeted user within the recent window",
    )
    @discord.app_commands.describe(
        member="Target user whose messages should be purged",
        amount="Maximum number of messages to scan (default: 100)",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def purge_user_cmd(
        self,
        ctx: Context,
        member: discord.Member | discord.User,
        amount: int = 100,
    ):
        """Delete messages strictly from a targeted user within the recent window."""
        if amount < 1:
            await ctx.send(
                embed=error_embed(description="Scan amount must be at least 1 message."),
                ephemeral=True,
            )
            return

        if ctx.interaction is None:
            with contextlib.suppress(discord.NotFound, discord.Forbidden):
                await ctx.message.delete()

        count = await purge_user_messages(
            ctx.channel,
            user_id=member.id,
            amount=min(amount, 1000),
            reason=f"Purge user {member} requested by {ctx.author}",
        )
        embed = success_embed(
            title="User Messages Cleared",
            description=f"Cleared **{count}** messages from {member.mention}.",
        )
        await ctx.send(embed=embed, delete_after=5)

    @purge.command(
        name="bot",
        description="Clean up messages sent by bots and bot command invocations",
    )
    @discord.app_commands.describe(
        amount="Maximum number of messages to scan (default: 100)",
        prefix="Optional custom command prefix to clean (default: server prefix)",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def purge_bot_cmd(
        self,
        ctx: Context,
        amount: int = 100,
        prefix: str | None = None,
    ):
        """Clean up only bot commands and bot responses."""
        if amount < 1:
            await ctx.send(
                embed=error_embed(description="Scan amount must be at least 1 message."),
                ephemeral=True,
            )
            return

        resolved_prefix = prefix or await self.bot.guild_repo.get_prefix(ctx.guild.id, default="!")

        if ctx.interaction is None:
            with contextlib.suppress(discord.NotFound, discord.Forbidden):
                await ctx.message.delete()

        count = await purge_bot_messages(
            ctx.channel,
            amount=min(amount, 1000),
            prefix=resolved_prefix,
            reason=f"Purge bot messages requested by {ctx.author}",
        )
        embed = success_embed(
            title="Bot Messages Cleared",
            description=f"Cleared **{count}** bot messages and commands.",
        )
        await ctx.send(embed=embed, delete_after=5)

    @purge.command(
        name="contains",
        description="Clear messages containing specific words or spam patterns",
    )
    @discord.app_commands.describe(
        text="The keyword, link, or phrase to match against",
        amount="Maximum number of messages to scan (default: 100)",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def purge_contains_cmd(
        self,
        ctx: Context,
        text: str,
        amount: int = 100,
    ):
        """Clear messages containing specific words or spam patterns."""
        if not text.strip():
            await ctx.send(
                embed=error_embed(description="Match text cannot be empty."),
                ephemeral=True,
            )
            return
        if amount < 1:
            await ctx.send(
                embed=error_embed(description="Scan amount must be at least 1 message."),
                ephemeral=True,
            )
            return

        if ctx.interaction is None:
            with contextlib.suppress(discord.NotFound, discord.Forbidden):
                await ctx.message.delete()

        count = await purge_containing_text(
            ctx.channel,
            text=text,
            amount=min(amount, 1000),
            reason=f"Purge text matching '{text}' requested by {ctx.author}",
        )
        embed = success_embed(
            title="Pattern Messages Cleared",
            description=f"Cleared **{count}** messages containing `{text}`.",
        )
        await ctx.send(embed=embed, delete_after=5)

    @purge.command(
        name="embeds",
        description="Delete messages containing rich links, embeds, or cards",
    )
    @discord.app_commands.describe(amount="Maximum number of messages to scan (default: 100)")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def purge_embeds_cmd(self, ctx: Context, amount: int = 100):
        """Delete messages containing rich link previews or embeds."""
        if amount < 1:
            await ctx.send(
                embed=error_embed(description="Scan amount must be at least 1 message."),
                ephemeral=True,
            )
            return

        if ctx.interaction is None:
            with contextlib.suppress(discord.NotFound, discord.Forbidden):
                await ctx.message.delete()

        count = await purge_embed_messages(
            ctx.channel,
            amount=min(amount, 1000),
            reason=f"Purge embeds requested by {ctx.author}",
        )
        embed = success_embed(
            title="Embed Messages Cleared",
            description=f"Cleared **{count}** messages containing embeds or link previews.",
        )
        await ctx.send(embed=embed, delete_after=5)

    @purge.command(
        name="files",
        description="Delete image spam, uploads, or file attachments",
    )
    @discord.app_commands.describe(amount="Maximum number of messages to scan (default: 100)")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def purge_files_cmd(self, ctx: Context, amount: int = 100):
        """Delete image spam or file attachments."""
        if amount < 1:
            await ctx.send(
                embed=error_embed(description="Scan amount must be at least 1 message."),
                ephemeral=True,
            )
            return

        if ctx.interaction is None:
            with contextlib.suppress(discord.NotFound, discord.Forbidden):
                await ctx.message.delete()

        count = await purge_file_messages(
            ctx.channel,
            amount=min(amount, 1000),
            reason=f"Purge files requested by {ctx.author}",
        )
        embed = success_embed(
            title="File Uploads Cleared",
            description=f"Cleared **{count}** messages with attachments or file uploads.",
        )
        await ctx.send(embed=embed, delete_after=5)

    @purge.command(
        name="after",
        description="Clean all messages posted between a target message ID and the current time",
    )
    @discord.app_commands.describe(
        message_id="The target Discord message ID to clean after",
        limit="Maximum number of messages to purge (default: 500)",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def purge_after_cmd(
        self,
        ctx: Context,
        message_id: str,
        limit: int = 500,
    ):
        """Clean all messages posted between a target message ID and the current time."""
        clean_id = message_id.strip()
        if not clean_id.isdigit():
            await ctx.send(
                embed=error_embed(
                    description="Invalid message ID. Message ID must be a numeric integer."
                ),
                ephemeral=True,
            )
            return

        target_id = int(clean_id)

        if ctx.interaction is None:
            with contextlib.suppress(discord.NotFound, discord.Forbidden):
                await ctx.message.delete()

        count = await purge_messages_after(
            ctx.channel,
            message_id=target_id,
            limit=min(limit, 1000),
            reason=f"Purge after message {target_id} requested by {ctx.author}",
        )
        embed = success_embed(
            title="Messages Cleared",
            description=f"Cleared **{count}** messages posted after message ID `{target_id}`.",
        )
        await ctx.send(embed=embed, delete_after=5)


async def setup(bot: DiscordBot):
    """Register Cleanup cog."""
    await bot.add_cog(Cleanup(bot))
