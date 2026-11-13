"""Core moderation enforcement toolkit and role authority configuration."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
import humanize
from discord.ext import commands, tasks
from discord.ext.commands import Context

from core import checks, exceptions
from core.embeds import (
    EmbedColor,
    error_embed,
    info_embed,
    make_embed,
    success_embed,
)
from core.logger import get_logger
from core.time import parse_duration
from services.moderation import (
    ban_member,
    hackban_user,
    kick_member,
    massban_users,
    softban_member,
    tempban_member,
    unban_member,
)
from views.confirm import ConfirmView

if TYPE_CHECKING:
    from bot import DiscordBot

logger = get_logger()


class Moderation(commands.Cog, name="moderation"):
    """Core Moderation Commands"""

    def __init__(self, bot: DiscordBot):
        self.bot = bot

    async def cog_load(self) -> None:
        """Start background workers when cog is loaded into the bot."""
        self.tempban_unban_worker.start()

    async def cog_unload(self) -> None:
        """Cancel background tasks when the cog is unloaded."""
        self.tempban_unban_worker.cancel()

    @tasks.loop(seconds=30.0)
    async def tempban_unban_worker(self) -> None:
        """Periodic background worker checking and unbanning expired tempbans."""
        now = datetime.now(UTC)
        expired = await self.bot.tempban_repo.get_expired_tempbans(now)
        for guild_id, user_id, reason in expired:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            with contextlib.suppress(discord.NotFound, discord.Forbidden, discord.HTTPException):
                await guild.unban(discord.Object(id=user_id), reason=f"Tempban expired: {reason}")
            await self.bot.tempban_repo.remove_tempban(guild_id, user_id)
            logger.info("tempban_expired_unbanned", guild_id=guild_id, user_id=user_id)

    @tempban_unban_worker.before_loop
    async def before_tempban_worker(self) -> None:
        """Wait until bot cache is ready before executing background unbans."""
        await self.bot.wait_until_ready()

    async def cog_check(self, ctx: Context) -> bool:
        """Verify the moderation module is enabled for the invoking guild."""
        if not ctx.guild:
            return True
        if ctx.bot.config.is_owner(ctx.author.id) or ctx.author.guild_permissions.administrator:
            return True
        is_enabled = await ctx.bot.guild_repo.is_module_enabled(ctx.guild.id, "moderation")
        if not is_enabled:
            raise exceptions.ModuleDisabled("moderation")
        return True

    @commands.hybrid_command(
        name="say",
        description="The bot will say anything you want",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def say(self, ctx: Context, *, sentence: str):
        """The bot will say anything you want."""
        await ctx.send(sentence)

    @commands.hybrid_command(
        name="embed",
        description="The bot will say anything you want in embeds",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def embed(self, ctx: Context, *, sentence: str):
        """The bot will say anything you want in embeds."""
        embed = success_embed(description=sentence)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="kick", description="Kick a user out of the server")
    @commands.guild_only()
    @checks.mod_or_permissions(kick_members=True)
    async def kick(
        self,
        ctx: Context,
        member: discord.Member,
        *,
        reason: str = "Not specified",
    ):
        """Kick a user out of the server."""
        try:
            case = await kick_member(ctx, member, reason)
            embed = success_embed(
                title="User Kicked!",
                description=(
                    f"**{member}** was kicked by **{ctx.author}**! (Case #{case.case_number})"
                ),
                fields=[("Reason", reason, False)],
            )
            await ctx.send(embed=embed)
        except exceptions.HierarchyError as e:
            embed = error_embed(title="Hierarchy Error", description=str(e))
            await ctx.send(embed=embed)
        except discord.Forbidden:
            embed = error_embed(
                description=(
                    f"An error occurred while trying to kick {member.mention}. "
                    "Make sure my role is higher than the member you want to kick."
                )
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="ban", description="Bans a user from the server")
    @commands.guild_only()
    @checks.mod_or_permissions(ban_members=True)
    async def ban(
        self,
        ctx: Context,
        member: discord.Member,
        *,
        reason: str = "Not specified",
    ):
        """Bans a user from the server."""
        try:
            case = await ban_member(ctx, member, reason)
            embed = success_embed(
                title="User Banned!",
                description=(
                    f"**{member}** was banned by **{ctx.author}**! (Case #{case.case_number})"
                ),
                fields=[("Reason", reason, False)],
            )
            await ctx.send(embed=embed)
        except exceptions.HierarchyError as e:
            embed = error_embed(title="Hierarchy Error", description=str(e))
            await ctx.send(embed=embed)
        except discord.Forbidden:
            embed = error_embed(
                description=(
                    f"An error occurred while trying to ban {member.mention}. "
                    "Make sure my role is higher than the member you want to ban."
                )
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="softban",
        description="Bans and immediately unbans a user to purge recent chat messages",
    )
    @discord.app_commands.describe(
        member="The member to softban",
        days="Days of message history to purge (1 to 7, default: 1)",
        reason="Reason for the softban",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(ban_members=True)
    async def softban(
        self,
        ctx: Context,
        member: discord.Member,
        days: int = 1,
        *,
        reason: str = "Not specified",
    ):
        """Bans and immediately unbans a user to purge their recent chat messages."""
        if not 1 <= days <= 7:
            await ctx.send(embed=error_embed(description="Days to purge must be between 1 and 7."))
            return

        case = await softban_member(ctx, member, reason=reason, days=days)
        days_label = f"{days} day{'s' if days > 1 else ''}"
        embed = success_embed(
            title="User Softbanned",
            description=(
                f"**{member}** was softbanned by **{ctx.author}**!\n"
                f"(Purged {days_label} of messages • Case #{case.case_number})"
            ),
            fields=[("Reason", reason, False)],
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="tempban",
        description="Temporarily ban a user with automated expiration unban",
    )
    @discord.app_commands.describe(
        member="The member to temporarily ban",
        duration="Duration of the ban (e.g., 1h, 1d, 3d, 1w)",
        reason="Reason for the tempban",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(ban_members=True)
    async def tempban(
        self,
        ctx: Context,
        member: discord.Member,
        duration: str,
        *,
        reason: str = "Not specified",
    ):
        """Temporarily bans a member with automated unban after expiration."""
        delta = parse_duration(duration)
        if not delta:
            await ctx.send(
                embed=error_embed(
                    description=(
                        f"Invalid duration format: `{duration}`. "
                        "Please use formats like `30m`, `2h`, `1d`, `7d`, or `2w`."
                    )
                )
            )
            return

        case, unban_at = await tempban_member(ctx, member, duration=delta, reason=reason)
        unban_ts = int(unban_at.timestamp())
        embed = success_embed(
            title="User Temporarily Banned",
            description=(
                f"**{member}** was tempbanned by **{ctx.author}**! (Case #{case.case_number})"
            ),
            fields=[
                ("Duration", humanize.precisedelta(delta), True),
                ("Expires", f"<t:{unban_ts}:R> (<t:{unban_ts}:F>)", True),
                ("Reason", reason, False),
            ],
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="unban",
        description="Unban a user by ID with optional one-time reinvite link",
    )
    @discord.app_commands.describe(
        user_id="The Discord user ID to unban",
        reinvite="Whether to create and DM a one-time server invite link",
        reason="Reason for unbanning",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(ban_members=True)
    async def unban(
        self,
        ctx: Context,
        user_id: str,
        reinvite: bool = False,
        *,
        reason: str = "Not specified",
    ):
        """Unbans a user by their user ID with optional invite link delivery."""
        clean_id = user_id.strip()
        if not clean_id.isdigit():
            await ctx.send(embed=error_embed(description="Invalid user ID provided."))
            return

        target_id = int(clean_id)
        user, reinvited, case = await unban_member(
            ctx, user_id=target_id, reinvite=reinvite, reason=reason
        )

        display_name = f"**{user.name}** (`{user.id}`)" if user else f"User ID `{target_id}`"
        fields: list[tuple[str, str, bool]] = [("Reason", reason, False)]
        if reinvite:
            status_text = "Delivered via DM" if reinvited else "Failed (DMs disabled)"
            fields.append(("One-Time Reinvite", status_text, True))

        case_info = f" (Case #{case.case_number})" if case else ""
        embed = success_embed(
            title="User Unbanned",
            description=f"{display_name} was unbanned by **{ctx.author}**!{case_info}",
            fields=fields,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="hackban",
        description="Pre-ban a malicious user ID before they join the server",
    )
    @discord.app_commands.describe(
        user_id="The numeric Discord user ID to pre-ban",
        reason="Reason for pre-ban",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(ban_members=True)
    async def hackban(
        self,
        ctx: Context,
        user_id: str,
        *,
        reason: str = "Pre-emptive hackban",
    ):
        """Bans a user ID before they join the guild."""
        clean_id = user_id.strip()
        if not clean_id.isdigit():
            await ctx.send(embed=error_embed(description="User ID must be numeric."))
            return

        target_id = int(clean_id)
        user, case = await hackban_user(ctx, user_id=target_id, reason=reason)
        display = f"**{user}** (`{user.id}`)" if user else f"User ID `{target_id}`"
        embed = success_embed(
            title="User Pre-emptively Banned",
            description=f"{display} was banned by **{ctx.author}**! (Case #{case.case_number})",
            fields=[("Reason", reason, False)],
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="massban",
        description="Ban multiple user IDs in bulk with interactive confirmation",
    )
    @discord.app_commands.describe(
        user_ids="Space-separated Discord user IDs to ban",
        reason="Reason for mass ban",
    )
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def massban(
        self,
        ctx: Context,
        user_ids: str,
        *,
        reason: str = "Massban operation",
    ):
        """Ban multiple user IDs in bulk with ConfirmView safety."""
        raw_ids = user_ids.replace(",", " ").split()
        valid_ids: list[int] = []
        for raw in raw_ids:
            if raw.isdigit():
                valid_ids.append(int(raw))

        if not valid_ids:
            await ctx.send(embed=error_embed(description="No valid numeric user IDs provided."))
            return

        valid_ids = list(dict.fromkeys(valid_ids))

        view = ConfirmView(
            invoker_id=ctx.author.id,
            confirm_label=f"Massban {len(valid_ids)} Users",
        )
        prompt_embed = make_embed(
            title="⚠️ Confirm Mass Ban",
            description=(
                f"Are you sure you want to permanently ban **{len(valid_ids)}** user(s)?\n"
                f"**Reason:** {reason}\n\n"
                "This action cannot be undone automatically."
            ),
            color=EmbedColor.WARNING,
        )
        prompt_msg = await ctx.send(embed=prompt_embed, view=view)
        await view.wait()

        if not view.value:
            cancel_embed = make_embed(
                title="Mass Ban Cancelled",
                description="The mass ban operation was aborted.",
                color=EmbedColor.INFO,
            )
            await prompt_msg.edit(embed=cancel_embed, view=None)
            return

        banned, failed = await massban_users(ctx, user_ids=valid_ids, reason=reason)
        banned_preview = ", ".join(str(uid) for uid in banned[:15])
        if len(banned) > 15:
            banned_preview += f" ...and {len(banned) - 15} more"

        result_embed = success_embed(
            title="Mass Ban Complete",
            description=(
                f"Successfully banned **{len(banned)}** users. Failed: **{len(failed)}**."
            ),
            fields=[
                ("Banned IDs", f"`{banned_preview}`" if banned else "None", False),
                ("Reason", reason, False),
            ],
        )
        await prompt_msg.edit(embed=result_embed, view=None)

    @commands.hybrid_group(
        name="roles",
        description="Manage administrative and moderator roles for this server",
    )
    @commands.guild_only()
    async def roles(self, ctx: Context):
        """Manage administrative and moderator roles for this server."""
        if ctx.invoked_subcommand is None:
            embed = info_embed(
                title="Server Role Configuration",
                description=(
                    "Subcommands available:\n"
                    "• `/roles add <type> <role>`: Add an Administrator or Moderator role\n"
                    "• `/roles remove <type> <role>`: Remove a registered role\n"
                    "• `/roles list`: List all configured roles"
                ),
            )
            await ctx.send(embed=embed)

    @roles.command(
        name="add",
        description="Configure an Administrator or Moderator role for the bot",
    )
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def roles_add(self, ctx: Context, role_type: str, role: discord.Role):
        """Add a role to the guild's administrator or moderator list."""
        normalized_type = role_type.lower()
        if normalized_type not in ("admin", "administrator", "mod", "moderator"):
            embed = error_embed(
                title="Invalid Role Type",
                description="Role type must be either `admin` or `mod`.",
            )
            await ctx.send(embed=embed)
            return

        stored_type = "admin" if normalized_type in ("admin", "administrator") else "mod"
        await self.bot.guild_repo.add_role(ctx.guild.id, role.id, stored_type)
        embed = success_embed(
            title="Role Configured",
            description=(
                f"Successfully registered {role.mention} as a **{stored_type.upper()}** role."
            ),
        )
        await ctx.send(embed=embed)

    @roles.command(
        name="remove",
        description="Remove an Administrator or Moderator role configuration",
    )
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def roles_remove(self, ctx: Context, role_type: str, role: discord.Role):
        """Remove a role from the guild's administrator or moderator list."""
        normalized_type = role_type.lower()
        if normalized_type not in ("admin", "administrator", "mod", "moderator"):
            embed = error_embed(
                title="Invalid Role Type",
                description="Role type must be either `admin` or `mod`.",
            )
            await ctx.send(embed=embed)
            return

        stored_type = "admin" if normalized_type in ("admin", "administrator") else "mod"
        removed = await self.bot.guild_repo.remove_role(ctx.guild.id, role.id, stored_type)
        if removed:
            embed = success_embed(
                title="Role Removed",
                description=(
                    f"Successfully removed {role.mention} from **{stored_type.upper()}** roles."
                ),
            )
        else:
            embed = error_embed(
                title="Role Not Found",
                description=(
                    f"{role.mention} is not registered as a {stored_type.capitalize()} role."
                ),
            )
        await ctx.send(embed=embed)

    @roles.command(name="list", description="List configured administrator and moderator roles")
    @commands.guild_only()
    @checks.mod_or_permissions()
    async def roles_list(self, ctx: Context):
        """List configured administrator and moderator roles for this server."""
        roles_dict = await self.bot.guild_repo.get_all_roles(ctx.guild.id)

        admin_roles: list[str] = []
        for role_id in roles_dict.get("admin", set()):
            role = ctx.guild.get_role(role_id)
            admin_roles.append(role.mention if role else f"`{role_id}` (deleted)")

        mod_roles: list[str] = []
        for role_id in roles_dict.get("mod", set()):
            role = ctx.guild.get_role(role_id)
            mod_roles.append(role.mention if role else f"`{role_id}` (deleted)")

        embed = info_embed(
            title=f"Configured Roles: {ctx.guild.name}",
            fields=[
                (
                    "Administrator Roles",
                    ", ".join(admin_roles) if admin_roles else "None configured",
                    False,
                ),
                (
                    "Moderator Roles",
                    ", ".join(mod_roles) if mod_roles else "None configured",
                    False,
                ),
            ],
        )
        await ctx.send(embed=embed)


async def setup(bot: DiscordBot):
    """Add Moderation commands to cogs"""
    await bot.add_cog(Moderation(bot))
