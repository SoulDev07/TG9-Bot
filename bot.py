"""TG9 Discord Bot - Main Entry Point."""

from __future__ import annotations

import asyncio
import os
import platform
import random
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, override

import discord
from discord.ext import commands, tasks
from discord.ext.commands import Context

from core.prefix import dynamic_prefix_resolver
from core.tree import BotCommandTree
from helpers import exceptions
from helpers.config import BotConfig, load_config
from helpers.db import (
    BlacklistRepository,
    DatabaseManager,
    GuildRepository,
    ModCaseRepository,
    TempBanRepository,
    WarningRepository,
)
from helpers.embeds import error_embed, warning_embed
from helpers.logger import get_logger, setup_logging

if TYPE_CHECKING:
    from discord import app_commands

logger = get_logger()

intents = discord.Intents.default()
intents.message_content = True


class DiscordBot(commands.Bot):
    """Core TG9 Bot instance managing cogs and lifecycle events."""

    def __init__(self, bot_config: BotConfig) -> None:
        super().__init__(
            command_prefix=dynamic_prefix_resolver,
            intents=intents,
            help_command=None,
            tree_cls=BotCommandTree,
        )
        self.config: BotConfig = bot_config
        self.start_time: datetime = datetime.now(UTC)

        self.db = DatabaseManager(db_path=bot_config.database_path)
        self.guild_repo = GuildRepository(self.db)
        self.blacklist_repo = BlacklistRepository(self.db)
        self.mod_case_repo = ModCaseRepository(self.db)
        self.tempban_repo = TempBanRepository(self.db)
        self.warning_repo = WarningRepository(self.db)

    async def load_cogs(self) -> None:
        """Load all extension modules from the cogs directory."""
        cogs_dir = os.path.join(".", "cogs")
        is_dir = await asyncio.to_thread(os.path.isdir, cogs_dir)
        if not is_dir:
            logger.warning("cogs_directory_missing", path=cogs_dir)
            return

        files = await asyncio.to_thread(os.listdir, cogs_dir)
        for file in sorted(files):
            if file.endswith(".py") and not file.startswith("__"):
                extension = file[:-3]
                try:
                    await self.load_extension(f"cogs.{extension}")
                    logger.info("extension_loaded", extension=extension)
                except Exception as e:
                    logger.error(
                        "extension_load_failed",
                        extension=extension,
                        error=f"{type(e).__name__}: {e}",
                    )

    @tasks.loop(minutes=60.0)
    async def status_task(self) -> None:
        """Rotate the bot presence based on configured statuses."""
        statuses = self.config.statuses
        if statuses:
            status = random.choice(statuses)
            await self.change_presence(
                status=discord.Status.idle,
                activity=discord.Game(status),
            )

    @status_task.before_loop
    async def before_status_task(self) -> None:
        await self.wait_until_ready()

    @override
    async def setup_hook(self) -> None:
        """Initialize database schema, warm caches, and load cogs before connecting."""
        bot_name = self.user.name if self.user else "TG9-Bot"
        logger.info(
            "bot_starting",
            bot_name=bot_name,
            discord_version=discord.__version__,
            python_version=platform.python_version(),
            system=f"{platform.system()} {platform.release()}",
        )

        await self.db.initialize()
        await self.blacklist_repo.warm_cache()
        await self.load_cogs()

        if not self.status_task.is_running():
            self.status_task.start()

    @override
    async def close(self) -> None:
        """Gracefully terminate background tasks, database connections, and bot."""
        if self.status_task.is_running():
            self.status_task.cancel()
        await self.db.close()
        await super().close()

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Provision default settings when joining a new server."""
        settings = await self.guild_repo.get_or_create(
            guild.id,
            default_prefix=self.config.bot_prefix,
        )
        logger.info(
            "guild_joined",
            guild_name=guild.name,
            guild_id=guild.id,
            member_count=guild.member_count,
            prefix=settings.prefix,
        )

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Handle departure from a guild."""
        logger.info(
            "guild_removed",
            guild_name=guild.name,
            guild_id=guild.id,
        )

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user or message.author.bot:
            return

        if await self.blacklist_repo.is_blacklisted(message.author.id):
            return

        await self.process_commands(message)

    async def on_command_completion(self, ctx: Context) -> None:
        """Audit log successful prefix and hybrid command executions."""
        if not ctx.command:
            return
        executed_command = ctx.command.qualified_name

        logger.info(
            "command_executed",
            command=executed_command,
            guild=ctx.guild.name if ctx.guild else "DM",
            guild_id=ctx.guild.id if ctx.guild else None,
            channel_id=ctx.channel.id,
            author=str(ctx.author),
            author_id=ctx.author.id,
        )

    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: app_commands.Command | app_commands.ContextMenu,
    ) -> None:
        """Audit log successful slash command executions."""
        logger.info(
            "app_command_executed",
            command=command.qualified_name,
            guild=interaction.guild.name if interaction.guild else "DM",
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            user=str(interaction.user),
            user_id=interaction.user.id,
        )

    async def on_command_error(self, ctx: Context, error: Exception) -> None:
        """Centralized error handling and messaging for prefix/hybrid commands."""
        actual_error = getattr(error, "original", error)

        match actual_error:
            case commands.MissingRequiredArgument() as err:
                embed = error_embed(description=str(err).capitalize())
                await ctx.send(embed=embed)

            case commands.MissingPermissions() as err:
                missing_perms = ", ".join(err.missing_permissions)
                embed = error_embed(
                    description=(
                        f"You are missing permission `{missing_perms}` to execute this command!"
                    )
                )
                await ctx.send(embed=embed)

            case commands.BotMissingPermissions() as err:
                missing_perms = ", ".join(err.missing_permissions)
                embed = error_embed(
                    description=(
                        f"I am missing permission `{missing_perms}` to execute this command!"
                    )
                )
                await ctx.send(embed=embed)

            case commands.CommandOnCooldown() as err:
                minutes, seconds = divmod(err.retry_after, 60)
                hours, minutes = divmod(minutes, 60)
                hours %= 24
                time_parts: list[str] = []
                if round(hours) > 0:
                    time_parts.append(f"{round(hours)} hours")
                if round(minutes) > 0:
                    time_parts.append(f"{round(minutes)} minutes")
                time_parts.append(f"{round(seconds)} seconds")

                embed = warning_embed(
                    title="Cooldown!",
                    description=f"You can use this command again in {' '.join(time_parts)}.",
                )
                await ctx.send(embed=embed)

            case exceptions.ModuleDisabled() as err:
                embed = error_embed(
                    title="Module Disabled",
                    description=(
                        f"The **{err.module_name.capitalize()}** module is currently disabled "
                        "on this server."
                    ),
                )
                await ctx.send(embed=embed)

            case exceptions.UserNotOwner():
                embed = error_embed(description="You are not the owner of this bot!")
                await ctx.send(embed=embed)

            case exceptions.UserNotGuildOwner():
                embed = error_embed(
                    title="Server Owner Only",
                    description="You must be the server owner to execute this command!",
                )
                await ctx.send(embed=embed)

            case exceptions.MissingRoleOrPermission() as err:
                embed = error_embed(
                    title="Permission Denied",
                    description=str(err),
                )
                await ctx.send(embed=embed)

            case exceptions.HierarchyError() as err:
                embed = error_embed(
                    title="Hierarchy Violation",
                    description=str(err),
                )
                await ctx.send(embed=embed)

            case _:
                logger.error(
                    "command_error",
                    command=ctx.command.qualified_name if ctx.command else "unknown",
                    error=str(actual_error),
                )
                raise actual_error


async def main() -> None:
    """Application entrypoint managing lifecycle and configuration."""
    bot_config = load_config()
    setup_logging(
        log_level=bot_config.log_level,
        json_logs=bot_config.json_logs,
    )

    token = bot_config.token.get_secret_value()
    if not token:
        logger.critical(
            "missing_token",
            message="TOKEN environment variable is not set in .env",
        )
        sys.exit(1)

    async with DiscordBot(bot_config=bot_config) as bot:
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
