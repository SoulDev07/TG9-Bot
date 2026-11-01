"""TG9 Discord Bot - Main Entry Point."""

import asyncio
import os
import platform
import random
import sys

import discord
from discord.ext import commands, tasks
from discord.ext.commands import Context

from helpers import exceptions
from helpers.config import BotConfig, load_config
from helpers.logger import get_logger, setup_logging

logger = get_logger()

# Set up bot intents
intents = discord.Intents.default()
intents.message_content = True


class DiscordBot(commands.Bot):
    """Core TG9 Bot instance managing cogs and lifecycle events."""

    def __init__(self, bot_config: BotConfig) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned_or(bot_config.bot_prefix),
            intents=intents,
            help_command=None,
        )
        self.config: BotConfig = bot_config

    async def load_cogs(self) -> None:
        """
        Load extension modules (cogs) into the bot.

        This function loops through the 'cogs' directory and loads each valid extension.
        """
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
        """
        Task to change the bot's status every 60 minutes.

        This function selects a random status from the config and updates the bot's presence.
        """
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
        """
        Perform setup tasks before the bot connects to the gateway.
        Loads all cogs first to ensure application commands are registered.
        """
        bot_name = self.user.name if self.user else "TG9-Bot"
        logger.info(
            "bot_starting",
            bot_name=bot_name,
            discord_version=discord.__version__,
            python_version=platform.python_version(),
            system=f"{platform.system()} {platform.release()}",
        )

        # Load all cogs before any sync operations
        await self.load_cogs()

        # Start periodic presence update loop
        if not self.status_task.is_running():
            self.status_task.start()

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user or message.author.bot:
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

        elif isinstance(error, exceptions.UserNotOwner):
            embed = discord.Embed(
                description="You are not the owner of this bot!",
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
    """Async main entrypoint with safe lifecycle management and typed configuration."""
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
