"""Interactive embed builder and bot message editing commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from discord.ext.commands import Context

from core import checks
from core.embeds import error_embed, success_embed
from core.logger import get_logger
from views.builder import EmbedBuilderView

if TYPE_CHECKING:
    from bot import DiscordBot

logger = get_logger()


class Builder(commands.Cog, name="builder"):
    """Interactive Embed Builder & Message Editor"""

    def __init__(self, bot: DiscordBot):
        self.bot = bot

    @commands.hybrid_command(
        name="builder",
        aliases=["embedbuilder"],
        description="Launch the interactive modal-based embed builder with live preview",
    )
    @discord.app_commands.describe(title="Optional initial title for the embed")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def builder(self, ctx: Context, *, title: str | None = None):
        """Launch the interactive modal-based embed builder with live preview."""
        initial_embed = discord.Embed(
            title=title or "New Embed",
            description="Click **Content** to edit description, **Add Field** for sections, or **Images** for banners.",
            color=discord.Color(0x5865F2),
        )
        view = EmbedBuilderView(invoker_id=ctx.author.id, existing_embed=initial_embed)
        msg = await ctx.send(
            content="### 🛠️ Interactive Embed Builder (Live Preview)",
            embed=initial_embed,
            view=view,
            ephemeral=True,
        )
        view.message = msg

    @commands.hybrid_group(
        name="edit",
        description="Edit past messages or embeds sent by the bot",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def edit_group(self, ctx: Context):
        """Manage and edit messages previously sent by the bot."""
        if ctx.invoked_subcommand is None:
            embed = error_embed(
                title="Invalid Subcommand",
                description=(
                    "Available subcommands:\n"
                    "• `/edit message <message_id> <new_content> [channel]`\n"
                    "• `/edit embed <message_id> [channel]`"
                ),
            )
            await ctx.send(embed=embed, ephemeral=True)

    @edit_group.command(
        name="message",
        description="Edit the text content of a message previously sent by the bot",
    )
    @discord.app_commands.describe(
        message_id="The numeric ID of the bot message to edit",
        new_content="The new text content for the message",
        channel="The channel containing the message (defaults to current channel)",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def edit_message_cmd(
        self,
        ctx: Context,
        message_id: int,
        *,
        new_content: str,
        channel: discord.TextChannel | None = None,
    ):
        """Edit the text content of a message previously sent by the bot."""
        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel | discord.Thread):
            await ctx.send(
                embed=error_embed(description="Invalid channel provided."), ephemeral=True
            )
            return

        try:
            target_msg = await target_channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send(
                embed=error_embed(
                    description=f"Message `{message_id}` was not found in {target_channel.mention}."
                ),
                ephemeral=True,
            )
            return
        except discord.Forbidden:
            await ctx.send(
                embed=error_embed(
                    description=f"I do not have permission to read messages in {target_channel.mention}."
                ),
                ephemeral=True,
            )
            return

        if target_msg.author.id != self.bot.user.id:
            await ctx.send(
                embed=error_embed(description="I can only edit messages sent by me."),
                ephemeral=True,
            )
            return

        try:
            await target_msg.edit(content=new_content)
            logger.info("bot_message_edited", message_id=message_id, editor=str(ctx.author))
            await ctx.send(
                embed=success_embed(
                    title="Message Edited",
                    description=f"Successfully edited [message `{message_id}`]({target_msg.jump_url}) in {target_channel.mention}.",
                ),
                ephemeral=True,
            )
        except discord.Forbidden:
            await ctx.send(
                embed=error_embed(description="Missing permissions to edit message."),
                ephemeral=True,
            )
        except discord.HTTPException as err:
            await ctx.send(
                embed=error_embed(description=f"Failed to edit message: `{err}`"), ephemeral=True
            )

    @edit_group.command(
        name="embed",
        description="Launch the interactive editor to modify an existing bot embed",
    )
    @discord.app_commands.describe(
        message_id="The numeric ID of the embed message to edit",
        channel="The channel containing the message (defaults to current channel)",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def edit_embed_cmd(
        self,
        ctx: Context,
        message_id: int,
        channel: discord.TextChannel | None = None,
    ):
        """Launch the interactive editor to modify an existing bot embed."""
        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel | discord.Thread):
            await ctx.send(
                embed=error_embed(description="Invalid channel provided."), ephemeral=True
            )
            return

        try:
            target_msg = await target_channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send(
                embed=error_embed(
                    description=f"Message `{message_id}` was not found in {target_channel.mention}."
                ),
                ephemeral=True,
            )
            return
        except discord.Forbidden:
            await ctx.send(
                embed=error_embed(
                    description=f"I do not have permission to read messages in {target_channel.mention}."
                ),
                ephemeral=True,
            )
            return

        if target_msg.author.id != self.bot.user.id:
            await ctx.send(
                embed=error_embed(description="I can only edit embeds sent by me."),
                ephemeral=True,
            )
            return

        if not target_msg.embeds:
            await ctx.send(
                embed=error_embed(
                    description=f"Message `{message_id}` does not contain any embeds."
                ),
                ephemeral=True,
            )
            return

        existing_embed = target_msg.embeds[0]
        view = EmbedBuilderView(
            invoker_id=ctx.author.id,
            existing_embed=existing_embed,
            target_message=target_msg,
        )
        msg = await ctx.send(
            content=f"### 🛠️ Editing Embed for Message [`{message_id}`]({target_msg.jump_url})",
            embed=existing_embed,
            view=view,
            ephemeral=True,
        )
        view.message = msg


async def setup(bot: DiscordBot):
    """Register Builder cog."""
    await bot.add_cog(Builder(bot))
