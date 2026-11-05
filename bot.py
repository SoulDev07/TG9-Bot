"""TG9 Discord Bot - Main Entry Point."""

from __future__ import annotations

import asyncio
import os
import platform
import random
import sys
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ext.commands import Context

from helpers import exceptions
from helpers.config import BotConfig, load_config
from helpers.db import (
    BlacklistRepository,
    DatabaseManager,
    GuildRepository,
    ModCaseRepository,
)
from helpers.logger import get_logger, setup_logging

logger = get_logger()

intents = discord.Intents.default()
intents.message_content = True


async def get_prefix(bot: DiscordBot, message: discord.Message) -> list[str]:
    """Dynamically resolve command prefixes per guild with fallback to default."""
    default_prefix = bot.config.bot_prefix
    if not message.guild:
        return commands.when_mentioned_or(default_prefix)(bot, message)

    prefix = await bot.guild_repo.get_prefix(message.guild.id, default=default_prefix)
    return commands.when_mentioned_or(prefix)(bot, message)


class BotCommandTree(app_commands.CommandTree):
    """Custom command tree providing global interaction guards and error dispatching."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Global guard for slash commands, modals, and component interactions."""
        if interaction.user.bot:
            return False

        bot: DiscordBot = interaction.client  # type: ignore
        if await bot.blacklist_repo.is_blacklisted(interaction.user.id):
            embed = discord.Embed(
                title="Access Denied",
                description="You are globally blacklisted from interacting with this bot.",
                color=0xE02B2B,
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return False

        return True

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Centralized application command error handler for slash commands."""
        actual_error = getattr(error, "original", error)

        if isinstance(actual_error, exceptions.HierarchyError):
            embed = discord.Embed(
                title="Hierarchy Violation",
                description=str(actual_error),
                color=0xE02B2B,
            )
        elif isinstance(actual_error, exceptions.MissingRoleOrPermission):
            embed = discord.Embed(
                title="Permission Denied",
                description=str(actual_error),
                color=0xE02B2B,
            )
        elif isinstance(actual_error, exceptions.UserNotGuildOwner):
            embed = discord.Embed(
                title="Server Owner Only",
                description="You must be the server owner to execute this command!",
                color=0xE02B2B,
            )
        elif isinstance(actual_error, exceptions.ModuleDisabled):
            embed = discord.Embed(
                title="Module Disabled",
                description=(
                    f"The **{actual_error.module_name.capitalize()}** module is currently disabled "
                    "on this server."
                ),
                color=0xE02B2B,
            )
        elif isinstance(actual_error, exceptions.UserNotOwner):
            embed = discord.Embed(
                description="You are not the owner of this bot!",
                color=0xE02B2B,
            )
        elif isinstance(actual_error, app_commands.CommandOnCooldown):
            embed = discord.Embed(
                title="Cooldown!",
                description=(
                    f"You can use this command again in {actual_error.retry_after:.1f} seconds."
                ),
                color=0xE02B2B,
            )
        elif isinstance(actual_error, app_commands.MissingPermissions):
            missing_perms = ", ".join(actual_error.missing_permissions)
            embed = discord.Embed(
                title="Error!",
                description=(
                    f"You are missing permission `{missing_perms}` to execute this command!"
                ),
                color=0xE02B2B,
            )
        elif isinstance(actual_error, app_commands.BotMissingPermissions):
            missing_perms = ", ".join(actual_error.missing_permissions)
            embed = discord.Embed(
                title="Error!",
                description=(f"I am missing permission `{missing_perms}` to execute this command!"),
                color=0xE02B2B,
            )
        else:
            logger.error(
                "app_command_error",
                command=interaction.command.name if interaction.command else "unknown",
                error=str(actual_error),
            )
            embed = discord.Embed(
                title="Error!",
                description="An unexpected error occurred while executing this command.",
                color=0xE02B2B,
            )

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass


class DiscordBot(commands.Bot):
    """Core TG9 Bot instance managing cogs and lifecycle events."""

    def __init__(self, bot_config: BotConfig) -> None:
        super().__init__(
            command_prefix=get_prefix,
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

    async def load_cogs(self) -> None:
        """Load all extension modules from the cogs directory."""
        cogs_dir = os.path.join(".", "cogs")
        if not os.path.isdir(cogs_dir):
            logger.warning("cogs_directory_missing", path=cogs_dir)
            return

        for file in sorted(os.listdir(cogs_dir)):
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
        if not ctx.command:
            return
        executed_command = ctx.command.qualified_name.split(" ")[0]

        if ctx.guild is not None:
            logger.info(
                "command_executed",
                command=executed_command,
                guild=ctx.guild.name,
                guild_id=ctx.guild.id,
                author=str(ctx.author),
                author_id=ctx.author.id,
            )
        else:
            logger.info(
                "command_executed",
                command=executed_command,
                guild="DM",
                author=str(ctx.author),
                author_id=ctx.author.id,
            )

    async def on_command_error(self, ctx: Context, error: Exception) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="Error!",
                description=str(error).capitalize(),
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

        elif isinstance(error, commands.MissingPermissions):
            missing_perms = ", ".join(error.missing_permissions)
            embed = discord.Embed(
                title="Error!",
                description=(
                    f"You are missing the permission `{missing_perms}` to execute this command!"
                ),
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

        elif isinstance(error, commands.BotMissingPermissions):
            missing_perms = ", ".join(error.missing_permissions)
            embed = discord.Embed(
                title="Error!",
                description=(
                    f"I am missing the permission `{missing_perms}` to execute this command!"
                ),
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

        elif isinstance(error, commands.CommandOnCooldown):
            minutes, seconds = divmod(error.retry_after, 60)
            hours, minutes = divmod(minutes, 60)
            hours %= 24
            time_parts = []
            if round(hours) > 0:
                time_parts.append(f"{round(hours)} hours")
            if round(minutes) > 0:
                time_parts.append(f"{round(minutes)} minutes")
            time_parts.append(f"{round(seconds)} seconds")

            embed = discord.Embed(
                title="Cooldown!",
                description=f"You can use this command again in {' '.join(time_parts)}.",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

        elif isinstance(error, exceptions.ModuleDisabled):
            embed = discord.Embed(
                title="Module Disabled",
                description=(
                    f"The **{error.module_name.capitalize()}** module is currently disabled "
                    "on this server."
                ),
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

        elif isinstance(error, exceptions.UserNotOwner):
            embed = discord.Embed(
                description="You are not the owner of this bot!",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

        elif isinstance(error, exceptions.UserNotGuildOwner):
            embed = discord.Embed(
                title="Server Owner Only",
                description="You must be the server owner to execute this command!",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

        elif isinstance(error, exceptions.MissingRoleOrPermission):
            embed = discord.Embed(
                title="Permission Denied",
                description=str(error),
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

        elif isinstance(error, exceptions.HierarchyError):
            embed = discord.Embed(
                title="Hierarchy Violation",
                description=str(error),
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)
        else:
            logger.error(
                "command_error",
                command=ctx.command.qualified_name if ctx.command else "unknown",
                error=str(error),
            )
            raise error


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
