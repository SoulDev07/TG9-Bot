""" Version: 1.4 """

import os
import platform
import random
import sys
import discord
from discord.ext import commands, tasks
from discord.ext.commands import Context
from dotenv import load_dotenv
from helpers import exceptions, json_manager

GLOBAL_SYNC = False

# Load environment variables from .env file
load_dotenv()

# Check for the existence of config.json
config_path = os.path.join(".", "config.json")
if not os.path.isfile(config_path):
    sys.exit("ADD config.json file")
else:
    config = json_manager.load_config()

# Set up bot intents
intents = discord.Intents.default()
intents.message_content = True


class DiscordBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or(config["bot_prefix"]),
            intents=intents,
            help_command=None,  # Remove help command
        )
        self.config = config

    async def load_cogs(self):
        """
        Load extension modules (cogs) into the bot.

        This function loops through the 'cogs' directory and loads each valid extension.
        """
        for file in os.listdir("./cogs"):
            if file.endswith(".py"):
                extension = file[:-3]
                try:
                    await self.load_extension(f"cogs.{extension}")
                    print(f"Loaded extension '{extension}'")
                except Exception as e:
                    exception = f"{type(e).__name__}: {e}"
                    print(f"Failed to load extension {extension}\n{exception}")

    @tasks.loop(minutes=60.0)
    async def status_task(self):
        """
        Task to change the bot's status every 60 minutes.

        This function selects a random status from the config file and updates the bot's presence.
        """
        status = random.choice(self.config["statuses"])
        await self.change_presence(status=discord.Status.idle, activity=discord.Game(status))

    @status_task.before_loop
    async def before_status_task(self):
        await self.wait_until_ready()

    async def setup_hook(self):
        """
        Perform setup tasks when the bot is ready.
        """
        print("Bot:", self.user.name)
        print("discord.py API Version:", discord.__version__)
        print(f"Platform Info: Python-{platform.python_version()} {platform.system()} {platform.release()}")
        print("-----------------------------------------------------")

        if GLOBAL_SYNC:
            bot.tree.clear_commands(guild=None)
            await bot.tree.sync()
        else:
            guild = discord.Object(id=bot.config["test_guild"])
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)

        await self.load_cogs()
        self.status_task.start()

    async def on_message(self, message: discord.Message):
        if message.author == self.user or message.author.bot:
            return
        await self.process_commands(message)

    async def on_command_completion(self, ctx: Context):
        full_command_name = ctx.command.qualified_name
        split = full_command_name.split(" ")
        executed_command = str(split[0])

        if ctx.guild is not None:
            print(f"Executed {executed_command} command in {ctx.guild.name}"
                  f" [{ctx.guild.id}] by {ctx.author} [{ctx.author.id}]")
        else:
            print(f"Executed {executed_command} command by {ctx.author} ({ctx.author.id}) in Personal Chat")

    async def on_command_error(self, ctx: Context, error):
        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(title="Error!", description=str(error).capitalize(), color=0xE02B2B)
            await ctx.send(embed=embed)

        elif isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="Error!",
                description=f"You are missing the permission `{error.missing_perms}` to execute this command!",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

        elif isinstance(error, commands.BotMissingPermissions):
            embed = discord.Embed(
                description=f"I am missing the permission `{error.missing_permissions}` to execute this command!",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

        elif isinstance(error, commands.CommandOnCooldown):
            minutes, seconds = divmod(error.retry_after, 60)
            hours, minutes = divmod(minutes, 60)
            hours = hours % 24
            embed = discord.Embed(
                title="Cooldown!",
                description="You can use this command again in "
                f"{f'{round(hours)} hours' if round(hours) > 0 else ''} "
                f"{f'{round(minutes)} minutes' if round(minutes) > 0 else ''} "
                f"{f'{round(seconds)} seconds' if round(
                    seconds) > 0 else ''}.",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

        elif isinstance(error,  exceptions.UserNotOwner):
            embed = discord.Embed(description="You are not the owner of this bot!", color=0xE02B2B)
            await ctx.send(embed=embed)
        else:
            raise error


# Create an instance of the bot
bot = DiscordBot()

# Run the bot
bot.run(os.getenv("TOKEN"))
