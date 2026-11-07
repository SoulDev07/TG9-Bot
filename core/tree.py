"""Centralized application command tree and interaction error dispatcher."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, override

import discord
from discord import app_commands

from helpers import exceptions
from helpers.embeds import error_embed, warning_embed
from helpers.logger import get_logger

if TYPE_CHECKING:
    from bot import DiscordBot

logger = get_logger()


class BotCommandTree(app_commands.CommandTree):
    """Custom command tree providing global interaction guards and error dispatching."""

    @override
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Global guard for slash commands, modals, and component interactions."""
        if interaction.user.bot:
            return False

        bot: DiscordBot = interaction.client  # type: ignore
        if await bot.blacklist_repo.is_blacklisted(interaction.user.id):
            embed = error_embed(
                title="Access Denied",
                description="You are globally blacklisted from interacting with this bot.",
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return False

        return True

    @override
    async def on_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Centralized application command error handler for slash commands."""
        actual_error = getattr(error, "original", error)
        cmd_name = interaction.command.qualified_name if interaction.command else "unknown"

        match actual_error:
            case exceptions.HierarchyError() as err:
                embed = error_embed(title="Hierarchy Violation", description=str(err))
            case exceptions.MissingRoleOrPermission() as err:
                embed = error_embed(title="Permission Denied", description=str(err))
            case exceptions.UserNotGuildOwner():
                embed = error_embed(
                    title="Server Owner Only",
                    description="You must be the server owner to execute this command!",
                )
            case exceptions.ModuleDisabled() as err:
                embed = error_embed(
                    title="Module Disabled",
                    description=(
                        f"The **{err.module_name.capitalize()}** module is currently disabled "
                        "on this server."
                    ),
                )
            case exceptions.UserNotOwner():
                embed = error_embed(description="You are not the owner of this bot!")
            case app_commands.CommandOnCooldown() as err:
                embed = warning_embed(
                    title="Cooldown!",
                    description=f"You can use this command again in {err.retry_after:.1f} seconds.",
                )
            case app_commands.MissingPermissions() as err:
                missing = ", ".join(err.missing_permissions)
                embed = error_embed(
                    title="Error!",
                    description=f"You are missing permission `{missing}` to execute this command!",
                )
            case app_commands.BotMissingPermissions() as err:
                missing = ", ".join(err.missing_permissions)
                embed = error_embed(
                    title="Error!",
                    description=f"I am missing permission `{missing}` to execute this command!",
                )
            case _:
                logger.error(
                    "app_command_error",
                    command=cmd_name,
                    user=str(interaction.user),
                    user_id=interaction.user.id,
                    guild_id=interaction.guild_id,
                    error=str(actual_error),
                )
                embed = error_embed(
                    title="Error!",
                    description="An unexpected error occurred while executing this command.",
                )

        with contextlib.suppress(discord.HTTPException):
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
