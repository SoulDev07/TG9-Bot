"""Stores Owner commands of Bot"""

import discord
from discord.ext import commands
from discord.ext.commands import Context

from helpers import checks, json_manager
from helpers.logger import get_logger

logger = get_logger()


class Owner(commands.Cog, name="owner"):
    """Owner Commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="sync")
    @checks.is_owner()
    @commands.guild_only()
    async def sync(self, ctx: Context, scope: str = "guild"):
        """Sync application command tree. Scope options: 'guild' (default), 'global', 'clear'."""
        if scope == "global":
            synced = await self.bot.tree.sync()
            logger.info("global_commands_synced", count=len(synced), author=str(ctx.author))
            embed = discord.Embed(
                title="Global Sync Complete",
                description=f"Successfully synced `{len(synced)}` application commands globally.",
                color=0x42F56C,
            )
            await ctx.send(embed=embed)
        elif scope == "clear":
            self.bot.tree.clear_commands(guild=ctx.guild)
            await self.bot.tree.sync(guild=ctx.guild)
            logger.info("guild_commands_cleared", guild_id=ctx.guild.id, author=str(ctx.author))
            embed = discord.Embed(
                title="Guild Commands Cleared",
                description=f"Cleared all custom application commands in **{ctx.guild.name}**.",
                color=0x42F56C,
            )
            await ctx.send(embed=embed)
        else:
            self.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await self.bot.tree.sync(guild=ctx.guild)
            logger.info(
                "guild_commands_synced",
                count=len(synced),
                guild_id=ctx.guild.id,
                author=str(ctx.author),
            )
            embed = discord.Embed(
                title="Guild Sync Complete",
                description=(
                    f"Successfully synced `{len(synced)}` commands to **{ctx.guild.name}**."
                ),
                color=0x42F56C,
            )
            await ctx.send(embed=embed)

    @commands.command(name="shutdown", aliases=["sd", "sleep"])
    @checks.is_owner()
    async def shutdown(self, ctx: Context):
        """Make the bot shutdown"""
        logger.info("shutdown_invoked", author=str(ctx.author))
        embed = discord.Embed(description="Shutting down...", color=0x42F56C)
        await ctx.send(embed=embed)
        await self.bot.close()

    @commands.group(name="blacklist")
    @checks.is_owner()
    async def blacklist(self, ctx: Context):
        """Lets you add or remove a user from not being able to use the bot."""
        if ctx.invoked_subcommand is None:
            blacklist_data = json_manager.load_blacklist()
            embed = discord.Embed(
                title=f"There are currently {len(blacklist_data['ids'])} blacklisted",
                description=f"{', '.join(str(user_id) for user_id in blacklist_data['ids'])}",
                color=0x0000FF,
            )
            await ctx.send(embed=embed)

    @blacklist.command(name="add")
    @checks.is_owner()
    async def blacklist_add(self, ctx: Context, member: discord.Member | None = None):
        """Make a user unable to use the bot."""
        if member is None:
            embed = discord.Embed(
                title="Error!",
                description="Please specify a valid member to add to the blacklist.",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)
            return

        user_id = member.id
        try:
            blacklist_data = json_manager.load_blacklist()
            if user_id in blacklist_data["ids"]:
                embed = discord.Embed(
                    title="Error!",
                    description=f"**{member.name}** is already in the blacklist.",
                    color=0xE02B2B,
                )
                await ctx.send(embed=embed)
                return

            json_manager.add_user_to_blacklist(user_id)
            blacklist_data = json_manager.load_blacklist()
            logger.info("user_blacklisted", target_id=user_id, target_name=member.name)
            embed = discord.Embed(
                title="User Blacklisted",
                description=f"**{member.name}** has been successfully added to the blacklist",
                color=0x42F56C,
            )
            embed.set_footer(
                text=f"There are now {len(blacklist_data['ids'])} users in the blacklist"
            )
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error("blacklist_add_failed", target_id=user_id, error=str(e))
            embed = discord.Embed(
                title="Error!",
                description=(
                    "An unknown error occurred when trying to add "
                    f"**{member.name}** to the blacklist."
                ),
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

    @blacklist.command(name="remove")
    @checks.is_owner()
    async def blacklist_remove(self, ctx: Context, member: discord.Member | None = None):
        """Make a user able to use the bot again."""
        if member is None:
            embed = discord.Embed(
                title="Error!",
                description="Please specify a valid member to remove from the blacklist.",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)
            return

        user_id = member.id
        try:
            json_manager.remove_user_from_blacklist(user_id)
            blacklist_data = json_manager.load_blacklist()
            logger.info("user_unblacklisted", target_id=user_id, target_name=member.name)
            embed = discord.Embed(
                title="User removed from blacklist",
                description=f"**{member.name}** has been successfully removed from the blacklist",
                color=0x42F56C,
            )
            embed.set_footer(
                text=f"There are now {len(blacklist_data['ids'])} users in the blacklist"
            )
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error("blacklist_remove_failed", target_id=user_id, error=str(e))
            embed = discord.Embed(
                title="Error!",
                description=f"**{member.name}** is not in the blacklist.",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

    @commands.group(name="status")
    @checks.is_owner()
    async def status(self, ctx: Context):
        """Add or Remove a status from a list of statuses"""
        if ctx.invoked_subcommand is None:
            statuses = (
                self.bot.config.statuses
                if hasattr(self.bot, "config")
                else json_manager.load_config()["statuses"]
            )
            embed = discord.Embed(
                title=f"There are currently {len(statuses)} statuses",
                description=f"{', '.join(str(status_item) for status_item in statuses)}",
                color=0x0000FF,
            )
            await ctx.send(embed=embed)

    @status.command(name="add")
    @checks.is_owner()
    async def status_add(self, ctx: Context, sentence: str):
        """Add a status to the list of statuses"""
        try:
            current_statuses = (
                self.bot.config.statuses
                if hasattr(self.bot, "config")
                else json_manager.load_config()["statuses"]
            )
            if sentence in current_statuses:
                embed = discord.Embed(
                    title="Error!",
                    description=f"**{sentence}** is already in the statuses.",
                    color=0xE02B2B,
                )
                await ctx.send(embed=embed)
                return

            json_manager.add_status_to_config(sentence)
            if hasattr(self.bot, "config") and sentence not in self.bot.config.statuses:
                self.bot.config.statuses.append(sentence)

            statuses_count = len(self.bot.config.statuses) if hasattr(self.bot, "config") else 0
            logger.info("status_added", status=sentence)
            embed = discord.Embed(
                title="Status Added",
                description=f"**{sentence}** has been successfully added to the statuses.",
                color=0x42F56C,
            )
            embed.set_footer(text=f"There are now {statuses_count} statuses.")
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error("status_add_failed", status=sentence, error=str(e))
            embed = discord.Embed(
                title="Error!",
                description=(
                    f"An unknown error occurred when trying to add **{sentence}** to the statuses."
                ),
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

    @status.command(name="remove")
    @checks.is_owner()
    async def status_remove(self, ctx: Context, sentence: str):
        """Remove a status from the list of statuses"""
        try:
            json_manager.remove_status_from_config(sentence)
            if hasattr(self.bot, "config") and sentence in self.bot.config.statuses:
                self.bot.config.statuses.remove(sentence)

            statuses_count = len(self.bot.config.statuses) if hasattr(self.bot, "config") else 0
            logger.info("status_removed", status=sentence)
            embed = discord.Embed(
                title="Status removed from statuses",
                description=f"**{sentence}** has been successfully removed from the statuses.",
                color=0x42F56C,
            )
            embed.set_footer(text=f"There are now {statuses_count} statuses.")
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error("status_remove_failed", status=sentence, error=str(e))
            embed = discord.Embed(
                title="Error!",
                description=f"**{sentence}** is not in the statuses.",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

    @status.command(name="set")
    @checks.is_owner()
    async def status_set(self, ctx: Context, *, sentence: str):
        """Set the status of the bot"""
        try:
            await ctx.bot.change_presence(
                status=discord.Status.idle,
                activity=discord.Game(sentence),
            )
            logger.info("presence_updated", status=sentence)
            embed = discord.Embed(
                title="Status set",
                description=f"**{sentence}** has been successfully set to bot.",
                color=0x42F56C,
            )
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error("presence_update_failed", status=sentence, error=str(e))
            embed = discord.Embed(
                title="Error!",
                description=f"**{sentence}** was unable to be set.",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    """Add Owner commands to cogs"""
    await bot.add_cog(Owner(bot))
