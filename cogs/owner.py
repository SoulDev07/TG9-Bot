"""Owner administrative commands."""

import discord
from discord.ext import commands
from discord.ext.commands import Context

from helpers import checks
from helpers.logger import get_logger

logger = get_logger()


class Owner(commands.Cog, name="owner"):
    """Owner Commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="sync")
    @checks.is_owner()
    async def sync(self, ctx: Context, scope: str | None = None):
        """Sync application command tree across guild, global, or target guild scopes."""
        try:
            if scope == "global":
                synced = await self.bot.tree.sync()
                logger.info("global_commands_synced", count=len(synced), author=str(ctx.author))
                embed = discord.Embed(
                    title="Global Sync Complete",
                    description=(
                        f"Successfully synced `{len(synced)}` application commands globally."
                    ),
                    color=0x42F56C,
                )
                await ctx.send(embed=embed)

            elif scope == "clearglobal":
                self.bot.tree.clear_commands(guild=None)
                await self.bot.tree.sync()
                logger.info("global_commands_cleared", author=str(ctx.author))
                embed = discord.Embed(
                    title="Global Commands Cleared",
                    description="Cleared all global application commands.",
                    color=0x42F56C,
                )
                await ctx.send(embed=embed)

            elif scope == "clear":
                if not ctx.guild:
                    await ctx.send("Guild-level clear can only be used within a server.")
                    return
                self.bot.tree.clear_commands(guild=ctx.guild)
                await self.bot.tree.sync(guild=ctx.guild)
                logger.info(
                    "guild_commands_cleared",
                    guild_id=ctx.guild.id,
                    author=str(ctx.author),
                )
                embed = discord.Embed(
                    title="Guild Commands Cleared",
                    description=f"Cleared all application commands in **{ctx.guild.name}**.",
                    color=0x42F56C,
                )
                await ctx.send(embed=embed)

            elif scope and scope.isdigit():
                target_guild = discord.Object(id=int(scope))
                self.bot.tree.copy_global_to(guild=target_guild)
                synced = await self.bot.tree.sync(guild=target_guild)
                logger.info(
                    "target_guild_commands_synced",
                    count=len(synced),
                    target_guild_id=scope,
                    author=str(ctx.author),
                )
                embed = discord.Embed(
                    title="Target Guild Sync Complete",
                    description=f"Successfully synced `{len(synced)}` commands to Guild `{scope}`.",
                    color=0x42F56C,
                )
                await ctx.send(embed=embed)

            else:
                if not ctx.guild:
                    await ctx.send("Cannot sync to current guild outside a server. Use `global`.")
                    return
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

        except discord.HTTPException as e:
            logger.error("sync_http_error", error=str(e), author=str(ctx.author))
            embed = discord.Embed(
                title="Sync Failed",
                description=f"Discord API returned an error: `{e}`",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

    @commands.command(name="load")
    @checks.is_owner()
    async def load_extension(self, ctx: Context, extension: str):
        """Load an extension module."""
        ext = extension if extension.startswith("cogs.") else f"cogs.{extension}"
        try:
            await self.bot.load_extension(ext)
            logger.info("extension_loaded", extension=ext, author=str(ctx.author))
            embed = discord.Embed(
                title="Extension Loaded",
                description=f"Successfully loaded extension `{ext}`.",
                color=0x42F56C,
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error("extension_load_failed", extension=ext, error=str(e))
            embed = discord.Embed(
                title="Load Failed",
                description=f"Failed to load `{ext}`:\n```{type(e).__name__}: {e}```",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

    @commands.command(name="unload")
    @checks.is_owner()
    async def unload_extension(self, ctx: Context, extension: str):
        """Unload an extension module."""
        ext = extension if extension.startswith("cogs.") else f"cogs.{extension}"
        if ext == "cogs.owner":
            embed = discord.Embed(
                title="Action Denied",
                description="Cannot unload the `owner` extension as it handles management.",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)
            return

        try:
            await self.bot.unload_extension(ext)
            logger.info("extension_unloaded", extension=ext, author=str(ctx.author))
            embed = discord.Embed(
                title="Extension Unloaded",
                description=f"Successfully unloaded extension `{ext}`.",
                color=0x42F56C,
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error("extension_unload_failed", extension=ext, error=str(e))
            embed = discord.Embed(
                title="Unload Failed",
                description=f"Failed to unload `{ext}`:\n```{type(e).__name__}: {e}```",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

    @commands.command(name="reload")
    @checks.is_owner()
    async def reload_extension(self, ctx: Context, extension: str = "all"):
        """Reload an extension module or all modules."""
        if extension.lower() == "all":
            loaded_extensions = list(self.bot.extensions.keys())
            reloaded: list[str] = []
            failed: list[str] = []

            for ext in loaded_extensions:
                try:
                    await self.bot.reload_extension(ext)
                    reloaded.append(ext)
                except Exception as e:
                    logger.error("extension_reload_failed", extension=ext, error=str(e))
                    failed.append(f"`{ext}` ({type(e).__name__})")

            logger.info(
                "all_extensions_reloaded",
                reloaded_count=len(reloaded),
                failed_count=len(failed),
                author=str(ctx.author),
            )
            description = f"Successfully reloaded `{len(reloaded)}` extension(s)."
            if failed:
                description += "\nFailed extensions:\n" + "\n".join(failed)

            embed = discord.Embed(
                title="Reload Complete",
                description=description,
                color=0x42F56C if not failed else 0xF59E42,
            )
            await ctx.send(embed=embed)
            return

        ext = extension if extension.startswith("cogs.") else f"cogs.{extension}"
        try:
            await self.bot.reload_extension(ext)
            logger.info("extension_reloaded", extension=ext, author=str(ctx.author))
            embed = discord.Embed(
                title="Extension Reloaded",
                description=f"Successfully reloaded extension `{ext}`.",
                color=0x42F56C,
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error("extension_reload_failed", extension=ext, error=str(e))
            embed = discord.Embed(
                title="Reload Failed",
                description=f"Failed to reload `{ext}`:\n```{type(e).__name__}: {e}```",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)

    @commands.command(name="cogs", aliases=["extensions", "modules"])
    @checks.is_owner()
    async def list_cogs(self, ctx: Context):
        """List all currently loaded cogs and extensions."""
        cogs_list = []
        for name, cog in self.bot.cogs.items():
            command_count = len(cog.get_commands())
            cogs_list.append(f"• **{name}** (`{command_count}` commands)")

        extensions_list = [f"`{ext}`" for ext in self.bot.extensions]

        embed = discord.Embed(
            title="Loaded Cogs & Extensions",
            color=0x42F56C,
        )
        embed.add_field(
            name=f"Active Cogs ({len(cogs_list)})",
            value="\n".join(cogs_list) if cogs_list else "None",
            inline=False,
        )
        embed.add_field(
            name=f"Active Extensions ({len(extensions_list)})",
            value=", ".join(extensions_list) if extensions_list else "None",
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.command(name="shutdown", aliases=["sd", "sleep"])
    @checks.is_owner()
    async def shutdown(self, ctx: Context):
        """Terminate the bot process safely."""
        logger.info("shutdown_invoked", author=str(ctx.author))
        embed = discord.Embed(description="Shutting down...", color=0x42F56C)
        await ctx.send(embed=embed)
        await self.bot.close()

    @commands.group(name="blacklist")
    @checks.is_owner()
    async def blacklist(self, ctx: Context):
        """Manage global bot user blacklist."""
        if ctx.invoked_subcommand is None:
            entries = await self.bot.blacklist_repo.get_all()
            ids = [str(entry.user_id) for entry in entries]
            embed = discord.Embed(
                title=f"There are currently {len(ids)} blacklisted",
                description=f"{', '.join(ids)}" if ids else "No users are currently blacklisted.",
                color=0x0000FF,
            )
            await ctx.send(embed=embed)

    @blacklist.command(name="add")
    @checks.is_owner()
    async def blacklist_add(
        self,
        ctx: Context,
        member: discord.Member | None = None,
        *,
        reason: str = "No reason specified",
    ):
        """Add a user to the global blacklist."""
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
            if await self.bot.blacklist_repo.is_blacklisted(user_id):
                embed = discord.Embed(
                    title="Error!",
                    description=f"**{member.name}** is already in the blacklist.",
                    color=0xE02B2B,
                )
                await ctx.send(embed=embed)
                return

            await self.bot.blacklist_repo.add(user_id, reason=reason, created_by=ctx.author.id)
            total_count = await self.bot.blacklist_repo.count()
            logger.info("user_blacklisted", target_id=user_id, target_name=member.name)
            embed = discord.Embed(
                title="User Blacklisted",
                description=f"**{member.name}** has been successfully added to the blacklist.",
                color=0x42F56C,
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_footer(text=f"There are now {total_count} users in the blacklist")
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
        """Remove a user from the global blacklist."""
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
            removed = await self.bot.blacklist_repo.remove(user_id)
            if not removed:
                embed = discord.Embed(
                    title="Error!",
                    description=f"**{member.name}** is not in the blacklist.",
                    color=0xE02B2B,
                )
                await ctx.send(embed=embed)
                return

            total_count = await self.bot.blacklist_repo.count()
            logger.info("user_unblacklisted", target_id=user_id, target_name=member.name)
            embed = discord.Embed(
                title="User removed from blacklist",
                description=f"**{member.name}** has been successfully removed from the blacklist",
                color=0x42F56C,
            )
            embed.set_footer(text=f"There are now {total_count} users in the blacklist")
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
        """Manage rotating presence statuses."""
        if ctx.invoked_subcommand is None:
            statuses = self.bot.config.statuses
            embed = discord.Embed(
                title=f"There are currently {len(statuses)} statuses",
                description=f"{', '.join(str(item) for item in statuses)}",
                color=0x0000FF,
            )
            await ctx.send(embed=embed)

    @status.command(name="add")
    @checks.is_owner()
    async def status_add(self, ctx: Context, sentence: str):
        """Add a status to rotating presence list."""
        if sentence in self.bot.config.statuses:
            embed = discord.Embed(
                title="Error!",
                description=f"**{sentence}** is already in the statuses.",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)
            return

        self.bot.config.statuses.append(sentence)
        logger.info("status_added", status=sentence)
        embed = discord.Embed(
            title="Status Added",
            description=f"**{sentence}** has been successfully added to rotating statuses.",
            color=0x42F56C,
        )
        embed.set_footer(text=f"There are now {len(self.bot.config.statuses)} statuses.")
        await ctx.send(embed=embed)

    @status.command(name="remove")
    @checks.is_owner()
    async def status_remove(self, ctx: Context, sentence: str):
        """Remove a status from rotating presence list."""
        if sentence not in self.bot.config.statuses:
            embed = discord.Embed(
                title="Error!",
                description=f"**{sentence}** is not in the statuses.",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)
            return

        self.bot.config.statuses.remove(sentence)
        logger.info("status_removed", status=sentence)
        embed = discord.Embed(
            title="Status Removed",
            description=f"**{sentence}** has been successfully removed from rotating statuses.",
            color=0x42F56C,
        )
        embed.set_footer(text=f"There are now {len(self.bot.config.statuses)} statuses.")
        await ctx.send(embed=embed)

    @status.command(name="set")
    @checks.is_owner()
    async def status_set(self, ctx: Context, *, sentence: str):
        """Set immediate bot presence."""
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
    """Register Owner cog."""
    await bot.add_cog(Owner(bot))
