"""Centralized application command tree and interaction error dispatcher."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, override

import discord
from discord import app_commands

from helpers import exceptions
from helpers.embeds import EmbedFactory
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
            embed = EmbedFactory.error(
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

        if isinstance(actual_error, exceptions.HierarchyError):
            embed = EmbedFactory.error(
                title="Hierarchy Violation",
                description=str(actual_error),
            )
        elif isinstance(actual_error, exceptions.MissingRoleOrPermission):
            embed = EmbedFactory.error(
                title="Permission Denied",
                description=str(actual_error),
            )
        elif isinstance(actual_error, exceptions.UserNotGuildOwner):
            embed = EmbedFactory.error(
                title="Server Owner Only",
                description="You must be the server owner to execute this command!",
            )
        elif isinstance(actual_error, exceptions.ModuleDisabled):
            embed = EmbedFactory.error(
                title="Module Disabled",
                description=(
                    f"The **{actual_error.module_name.capitalize()}** module is currently disabled "
                    "on this server."
                ),
            )
        elif isinstance(actual_error, exceptions.UserNotOwner):
            embed = EmbedFactory.error(
                description="You are not the owner of this bot!",
            )
        elif isinstance(actual_error, app_commands.CommandOnCooldown):
            embed = EmbedFactory.warning(
                title="Cooldown!",
                description=(
                    f"You can use this command again in {actual_error.retry_after:.1f} seconds."
                ),
            )
        elif isinstance(actual_error, app_commands.MissingPermissions):
            missing_perms = ", ".join(actual_error.missing_permissions)
            embed = EmbedFactory.error(
                title="Error!",
                description=(
                    f"You are missing permission `{missing_perms}` to execute this command!"
                ),
            )
        elif isinstance(actual_error, app_commands.BotMissingPermissions):
            missing_perms = ", ".join(actual_error.missing_permissions)
            embed = EmbedFactory.error(
                title="Error!",
                description=(f"I am missing permission `{missing_perms}` to execute this command!"),
            )
        else:
            logger.error(
                "app_command_error",
                command=interaction.command.name if interaction.command else "unknown",
                error=str(actual_error),
            )
            embed = EmbedFactory.error(
                title="Error!",
                description="An unexpected error occurred while executing this command.",
            )

        with contextlib.suppress(discord.HTTPException):
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
