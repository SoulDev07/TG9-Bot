"""Owner administrative commands."""

from __future__ import annotations

import discord
from discord.ext import commands
from discord.ext.commands import Context

from core import checks
from core.embeds import error_embed, info_embed, make_embed, success_embed, warning_embed
from core.logger import get_logger

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
            match scope:
                case "global":
                    synced = await self.bot.tree.sync()
                    logger.info("global_commands_synced", count=len(synced), author=str(ctx.author))
                    embed = success_embed(
                        title="Global Sync Complete",
                        description=(
                            f"Successfully synced `{len(synced)}` application commands globally."
                        ),
                    )
                    await ctx.send(embed=embed)

                case "clearglobal":
                    self.bot.tree.clear_commands(guild=None)
                    await self.bot.tree.sync()
                    logger.info("global_commands_cleared", author=str(ctx.author))
                    embed = success_embed(
                        title="Global Commands Cleared",
                        description="Cleared all global application commands.",
                    )
                    await ctx.send(embed=embed)

                case "clear":
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
                    embed = success_embed(
                        title="Guild Commands Cleared",
                        description=f"Cleared all application commands in **{ctx.guild.name}**.",
                    )
                    await ctx.send(embed=embed)

                case str() if scope.isdigit():
                    target_guild = discord.Object(id=int(scope))
                    self.bot.tree.copy_global_to(guild=target_guild)
                    synced = await self.bot.tree.sync(guild=target_guild)
                    logger.info(
                        "target_guild_commands_synced",
                        count=len(synced),
                        target_guild_id=scope,
                        author=str(ctx.author),
                    )
                    embed = success_embed(
                        title="Target Guild Sync Complete",
                        description=(
                            f"Successfully synced `{len(synced)}` commands to Guild `{scope}`."
                        ),
                    )
                    await ctx.send(embed=embed)

                case _:
                    if not ctx.guild:
                        await ctx.send(
                            "Cannot sync to current guild outside a server. Use `global`."
                        )
                        return
                    self.bot.tree.copy_global_to(guild=ctx.guild)
                    synced = await self.bot.tree.sync(guild=ctx.guild)
                    logger.info(
                        "guild_commands_synced",
                        count=len(synced),
                        guild_id=ctx.guild.id,
                        author=str(ctx.author),
                    )
                    embed = success_embed(
                        title="Guild Sync Complete",
                        description=(
                            f"Successfully synced `{len(synced)}` commands to **{ctx.guild.name}**."
                        ),
                    )
                    await ctx.send(embed=embed)

        except discord.HTTPException as e:
            logger.error("sync_http_error", error=str(e), author=str(ctx.author))
            embed = error_embed(
                title="Sync Failed",
                description=f"Discord API returned an error: `{e}`",
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
            embed = success_embed(
                title="Extension Loaded",
                description=f"Successfully loaded extension `{ext}`.",
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error("extension_load_failed", extension=ext, error=str(e))
            embed = error_embed(
                title="Load Failed",
                description=f"Failed to load `{ext}`:\n```{type(e).__name__}: {e}```",
            )
            await ctx.send(embed=embed)

    @commands.command(name="unload")
    @checks.is_owner()
    async def unload_extension(self, ctx: Context, extension: str):
        """Unload an extension module."""
        ext = extension if extension.startswith("cogs.") else f"cogs.{extension}"
        if ext == "cogs.owner":
            embed = error_embed(
                title="Action Denied",
                description="Cannot unload the `owner` extension as it handles management.",
            )
            await ctx.send(embed=embed)
            return

        try:
            await self.bot.unload_extension(ext)
            logger.info("extension_unloaded", extension=ext, author=str(ctx.author))
            embed = success_embed(
                title="Extension Unloaded",
                description=f"Successfully unloaded extension `{ext}`.",
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error("extension_unload_failed", extension=ext, error=str(e))
            embed = error_embed(
                title="Unload Failed",
                description=f"Failed to unload `{ext}`:\n```{type(e).__name__}: {e}```",
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

            if failed:
                embed = warning_embed(title="Reload Complete", description=description)
            else:
                embed = success_embed(title="Reload Complete", description=description)
            await ctx.send(embed=embed)
            return

        ext = extension if extension.startswith("cogs.") else f"cogs.{extension}"
        try:
            await self.bot.reload_extension(ext)
            logger.info("extension_reloaded", extension=ext, author=str(ctx.author))
            embed = success_embed(
                title="Extension Reloaded",
                description=f"Successfully reloaded extension `{ext}`.",
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error("extension_reload_failed", extension=ext, error=str(e))
            embed = error_embed(
                title="Reload Failed",
                description=f"Failed to reload `{ext}`:\n```{type(e).__name__}: {e}```",
            )
            await ctx.send(embed=embed)

    @commands.command(name="cogs", aliases=["extensions"])
    @checks.is_owner()
    async def list_cogs(self, ctx: Context):
        """List all currently loaded cogs and extensions."""
        cogs_list = []
        for name, cog in self.bot.cogs.items():
            command_count = len(cog.get_commands())
            cogs_list.append(f"• **{name}** (`{command_count}` commands)")

        extensions_list = [f"`{ext}`" for ext in self.bot.extensions]

        embed = make_embed(
            title="Loaded Cogs & Extensions",
            fields=[
                (
                    f"Active Cogs ({len(cogs_list)})",
                    "\n".join(cogs_list) if cogs_list else "None",
                    False,
                ),
                (
                    f"Active Extensions ({len(extensions_list)})",
                    ", ".join(extensions_list) if extensions_list else "None",
                    False,
                ),
            ],
        )
        await ctx.send(embed=embed)

    @commands.command(name="shutdown", aliases=["sd", "sleep"])
    @checks.is_owner()
    async def shutdown(self, ctx: Context):
        """Terminate the bot process safely."""
        logger.info("shutdown_invoked", author=str(ctx.author))
        embed = success_embed(description="Shutting down...")
        await ctx.send(embed=embed)
        await self.bot.close()

    @commands.group(name="blacklist")
    @checks.is_owner()
    async def blacklist(self, ctx: Context):
        """Manage global bot user blacklist."""
        if ctx.invoked_subcommand is None:
            entries = await self.bot.blacklist_repo.get_all()
            ids = [str(entry.user_id) for entry in entries]
            embed = info_embed(
                title=f"There are currently {len(ids)} blacklisted users",
                description=f"{', '.join(ids)}" if ids else "No users are currently blacklisted.",
            )
            await ctx.send(embed=embed)

    @blacklist.command(name="add")
    @checks.is_owner()
    async def blacklist_add(
        self,
        ctx: Context,
        user: discord.User | None = None,
        *,
        reason: str = "No reason specified",
    ):
        """Add a user to the global blacklist."""
        if user is None:
            embed = error_embed(
                title="Error!",
                description="Please specify a valid user to add to the blacklist.",
            )
            await ctx.send(embed=embed)
            return

        user_id = user.id
        try:
            if await self.bot.blacklist_repo.is_blacklisted(user_id):
                embed = error_embed(
                    title="Error!",
                    description=f"**{user.name}** is already in the blacklist.",
                )
                await ctx.send(embed=embed)
                return

            await self.bot.blacklist_repo.add(user_id, reason=reason, created_by=ctx.author.id)
            total_count = await self.bot.blacklist_repo.count()
            logger.info("user_blacklisted", target_id=user_id, target_name=user.name)
            embed = success_embed(
                title="User Blacklisted",
                description=f"**{user.name}** has been successfully added to the blacklist.",
                fields=[("Reason", reason, False)],
                footer=f"There are now {total_count} users in the blacklist",
            )
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error("blacklist_add_failed", target_id=user_id, error=str(e))
            embed = error_embed(
                title="Error!",
                description=(
                    "An unknown error occurred when trying to add "
                    f"**{user.name}** to the blacklist."
                ),
            )
            await ctx.send(embed=embed)

    @blacklist.command(name="remove")
    @checks.is_owner()
    async def blacklist_remove(self, ctx: Context, user: discord.User | None = None):
        """Remove a user from the global blacklist."""
        if user is None:
            embed = error_embed(
                title="Error!",
                description="Please specify a valid user to remove from the blacklist.",
            )
            await ctx.send(embed=embed)
            return

        user_id = user.id
        try:
            removed = await self.bot.blacklist_repo.remove(user_id)
            if not removed:
                embed = error_embed(
                    title="Error!",
                    description=f"**{user.name}** is not in the blacklist.",
                )
                await ctx.send(embed=embed)
                return

            total_count = await self.bot.blacklist_repo.count()
            logger.info("user_unblacklisted", target_id=user_id, target_name=user.name)
            embed = success_embed(
                title="User removed from blacklist",
                description=f"**{user.name}** has been successfully removed from the blacklist",
                footer=f"There are now {total_count} users in the blacklist",
            )
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error("blacklist_remove_failed", target_id=user_id, error=str(e))
            embed = error_embed(
                title="Error!",
                description=f"**{user.name}** is not in the blacklist.",
            )
            await ctx.send(embed=embed)

    @commands.group(name="status")
    @checks.is_owner()
    async def status(self, ctx: Context):
        """Manage rotating presence statuses."""
        if ctx.invoked_subcommand is None:
            statuses = self.bot.config.statuses
            embed = info_embed(
                title=f"There are currently {len(statuses)} statuses",
                description=f"{', '.join(str(item) for item in statuses)}",
            )
            await ctx.send(embed=embed)

    @status.command(name="add")
    @checks.is_owner()
    async def status_add(self, ctx: Context, sentence: str):
        """Add a status to rotating presence list."""
        if sentence in self.bot.config.statuses:
            embed = error_embed(
                title="Error!",
                description=f"**{sentence}** is already in the statuses.",
            )
            await ctx.send(embed=embed)
            return

        self.bot.config.statuses.append(sentence)
        logger.info("status_added", status=sentence)
        embed = success_embed(
            title="Status Added",
            description=f"**{sentence}** has been successfully added to rotating statuses.",
            footer=f"There are now {len(self.bot.config.statuses)} statuses.",
        )
        await ctx.send(embed=embed)

    @status.command(name="remove")
    @checks.is_owner()
    async def status_remove(self, ctx: Context, sentence: str):
        """Remove a status from rotating presence list."""
        if sentence not in self.bot.config.statuses:
            embed = error_embed(
                title="Error!",
                description=f"**{sentence}** is not in the statuses.",
            )
            await ctx.send(embed=embed)
            return

        self.bot.config.statuses.remove(sentence)
        logger.info("status_removed", status=sentence)
        embed = success_embed(
            title="Status Removed",
            description=f"**{sentence}** has been successfully removed from rotating statuses.",
            footer=f"There are now {len(self.bot.config.statuses)} statuses.",
        )
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
            embed = success_embed(
                title="Status set",
                description=f"**{sentence}** has been successfully set to bot.",
            )
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error("presence_update_failed", status=sentence, error=str(e))
            embed = error_embed(
                title="Error!",
                description=f"**{sentence}** was unable to be set.",
            )
            await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    """Register Owner cog."""
    await bot.add_cog(Owner(bot))
