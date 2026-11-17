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
from core.time import format_duration, parse_duration
from services.moderation import (
    ban_member,
    hackban_user,
    kick_member,
    massban_users,
    softban_member,
    tempban_member,
    timeout_member,
    unban_member,
    untimeout_member,
)
from views.confirm import ConfirmView
from views.selfroles import PersistentSelfRoleView, SelfRoleSelectView

if TYPE_CHECKING:
    from bot import DiscordBot

logger = get_logger()


class Moderation(commands.Cog, name="moderation"):
    """Core Moderation Commands"""

    def __init__(self, bot: DiscordBot):
        self.bot = bot

    async def cog_load(self) -> None:
        """Start background workers and register persistent views when cog is loaded."""
        self.tempban_unban_worker.start()
        self.bot.add_view(PersistentSelfRoleView(self.bot))

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
            if guild:
                with contextlib.suppress(
                    discord.NotFound, discord.Forbidden, discord.HTTPException
                ):
                    unban_reason = f"Tempban expired: {reason}"
                    await guild.unban(discord.Object(id=user_id), reason=unban_reason)
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
        aliases=["echo"],
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

    @commands.hybrid_command(
        name="timeout",
        aliases=["mute"],
        description="Place a member in temporary server timeout",
    )
    @discord.app_commands.describe(
        member="The member to place in timeout",
        duration="Duration of timeout (e.g. '10m', '1h', '1d', max: 28 days)",
        reason="Reason for the timeout",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(moderate_members=True)
    async def timeout(
        self,
        ctx: Context,
        member: discord.Member,
        duration: str = "1h",
        *,
        reason: str = "Not specified",
    ):
        """Place a member in temporary server timeout."""
        parsed_delta = parse_duration(duration)
        if not parsed_delta:
            embed = error_embed(
                title="Invalid Duration",
                description=f"Invalid duration format: `{duration}`. Examples: `10m`, `1h`, `1d`.",
            )
            await ctx.send(embed=embed)
            return

        if parsed_delta.total_seconds() > 2419200:
            embed = error_embed(
                title="Invalid Duration",
                description="Timeout duration cannot exceed 28 days.",
            )
            await ctx.send(embed=embed)
            return

        try:
            case, readable_dur = await timeout_member(ctx, member, parsed_delta, reason)
            embed = success_embed(
                title="Member Timed Out",
                description=f"**{member}** was timed out by **{ctx.author}**! (Case #{case.case_number})",
                fields=[
                    ("Duration", readable_dur, True),
                    ("Reason", reason, False),
                ],
            )
            await ctx.send(embed=embed)
        except exceptions.HierarchyError as e:
            embed = error_embed(title="Hierarchy Error", description=str(e))
            await ctx.send(embed=embed)
        except discord.Forbidden:
            embed = error_embed(
                description=(
                    f"An error occurred while trying to timeout {member.mention}. "
                    "Make sure my role is higher than the target member's highest role."
                )
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="untimeout",
        aliases=["unmute"],
        description="Remove a temporary timeout from a member",
    )
    @discord.app_commands.describe(
        member="The member whose timeout to revoke",
        reason="Reason for removing the timeout",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(moderate_members=True)
    async def untimeout(
        self,
        ctx: Context,
        member: discord.Member,
        *,
        reason: str = "Timeout removed",
    ):
        """Remove a temporary timeout from a member."""
        try:
            case = await untimeout_member(ctx, member, reason)
            embed = success_embed(
                title="Timeout Revoked",
                description=f"Timeout removed for **{member}** by **{ctx.author}**! (Case #{case.case_number})",
                fields=[("Reason", reason, False)],
            )
            await ctx.send(embed=embed)
        except exceptions.HierarchyError as e:
            embed = error_embed(title="Hierarchy Error", description=str(e))
            await ctx.send(embed=embed)
        except discord.Forbidden:
            embed = error_embed(
                description=(
                    f"An error occurred while removing timeout for {member.mention}. "
                    "Make sure my role is higher than the target member's highest role."
                )
            )
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
        aliases=["role"],
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

    @commands.hybrid_command(
        name="slowmode",
        aliases=["sm"],
        description="Inspect or adjust the slowmode delay for a text channel",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    @discord.app_commands.describe(
        duration="Slowmode duration (e.g. '10s', '5m', '1h', or raw seconds). Omit to inspect current slowmode.",
        channel="Target channel to inspect or modify (defaults to current channel).",
    )
    async def slowmode(
        self,
        ctx: Context,
        duration: str | None = None,
        channel: discord.TextChannel | None = None,
    ):
        """Inspect or adjust the slowmode delay for a text channel."""
        target_channel = channel or (
            ctx.channel if isinstance(ctx.channel, discord.TextChannel) else None
        )
        if target_channel is None or not isinstance(
            target_channel, discord.TextChannel | discord.Thread
        ):
            embed = error_embed(
                title="Invalid Channel",
                description="Slowmode can only be configured for text channels and threads.",
            )
            await ctx.send(embed=embed)
            return

        if duration is None:
            current_delay = target_channel.slowmode_delay
            if current_delay == 0:
                embed = info_embed(
                    title="Slowmode Status",
                    description=f"Slowmode is currently **disabled** in {target_channel.mention}.",
                )
            else:
                formatted = format_duration(current_delay)
                embed = info_embed(
                    title="Slowmode Status",
                    description=(
                        f"Current slowmode in {target_channel.mention} is set to "
                        f"**{formatted}** (`{current_delay}` seconds)."
                    ),
                )
            await ctx.send(embed=embed)
            return

        clean_dur = duration.strip().lower()
        if clean_dur.isdigit():
            seconds = int(clean_dur)
        else:
            delta = parse_duration(clean_dur)
            if delta is None:
                embed = error_embed(
                    title="Invalid Duration Format",
                    description="Provide seconds as a number (e.g. `30`) or a formatted string (e.g. `10s`, `5m`, `1h`).",
                )
                await ctx.send(embed=embed)
                return
            seconds = int(delta.total_seconds())

        if seconds < 0 or seconds > 21600:
            embed = error_embed(
                title="Invalid Duration",
                description="Slowmode delay must be between `0` and `21600` seconds (6 hours).",
            )
            await ctx.send(embed=embed)
            return

        if not target_channel.permissions_for(ctx.guild.me).manage_channels:
            embed = error_embed(
                title="Missing Permissions",
                description=f"I do not have `Manage Channels` permission in {target_channel.mention}.",
            )
            await ctx.send(embed=embed)
            return

        try:
            await target_channel.edit(slowmode_delay=seconds)
            logger.info(
                "slowmode_updated",
                guild_id=ctx.guild.id,
                channel_id=target_channel.id,
                seconds=seconds,
                moderator=str(ctx.author),
            )
            if seconds == 0:
                embed = success_embed(
                    title="Slowmode Disabled",
                    description=f"Slowmode has been **disabled** in {target_channel.mention}.",
                )
            else:
                formatted = format_duration(seconds)
                embed = success_embed(
                    title="Slowmode Updated",
                    description=(
                        f"Slowmode in {target_channel.mention} has been set to "
                        f"**{formatted}** (`{seconds}s`)."
                    ),
                )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            embed = error_embed(
                title="Action Failed",
                description=f"Failed to update slowmode in {target_channel.mention} due to insufficient bot permissions.",
            )
            await ctx.send(embed=embed)
        except discord.HTTPException as err:
            embed = error_embed(
                title="Discord API Error",
                description=f"An error occurred while updating slowmode: `{err}`",
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="announce",
        aliases=["broadcast"],
        description="Broadcast a structured announcement to a server channel",
    )
    @commands.guild_only()
    @checks.admin_or_permissions(manage_messages=True)
    @discord.app_commands.describe(
        channel="Target text channel for the announcement",
        message="Announcement text content",
        title="Header title for the announcement embed",
        ping="Mention to include: none, everyone, or here",
        role="Optional role to ping with the announcement",
        as_embed="Send as a styled embed (True) or plain text message (False)",
    )
    async def announce(
        self,
        ctx: Context,
        channel: discord.TextChannel,
        *,
        message: str,
        title: str = "Server Announcement",
        ping: str = "none",
        role: discord.Role | None = None,
        as_embed: bool = True,
    ):
        """Broadcast a structured announcement to a server channel."""
        normalized_ping = ping.lower()
        if normalized_ping not in ("none", "everyone", "here"):
            embed = error_embed(
                title="Invalid Ping Option",
                description="Ping choice must be one of: `none`, `everyone`, or `here`.",
            )
            await ctx.send(embed=embed)
            return

        if (
            normalized_ping in ("everyone", "here")
            and not ctx.author.guild_permissions.mention_everyone
        ):
            embed = error_embed(
                title="Permission Denied",
                description="You need `Mention Everyone` permission to include `@everyone` or `@here` pings.",
            )
            await ctx.send(embed=embed)
            return

        if (
            role is not None
            and not ctx.author.guild_permissions.mention_everyone
            and not role.mentionable
        ):
            embed = error_embed(
                title="Permission Denied",
                description=f"You do not have permission to mention {role.mention}.",
            )
            await ctx.send(embed=embed)
            return

        bot_perms = channel.permissions_for(ctx.guild.me)
        if not bot_perms.send_messages:
            embed = error_embed(
                title="Missing Permissions",
                description=f"I do not have permission to send messages in {channel.mention}.",
            )
            await ctx.send(embed=embed)
            return

        if as_embed and not bot_perms.embed_links:
            embed = error_embed(
                title="Missing Permissions",
                description=f"I require `Embed Links` permission in {channel.mention} to deliver embed announcements.",
            )
            await ctx.send(embed=embed)
            return

        mentions_list: list[str] = []
        if normalized_ping == "everyone":
            mentions_list.append("@everyone")
        elif normalized_ping == "here":
            mentions_list.append("@here")
        if role is not None:
            mentions_list.append(role.mention)

        mention_str = " ".join(mentions_list) if mentions_list else None

        allowed_mentions = discord.AllowedMentions(
            everyone=(normalized_ping in ("everyone", "here")),
            roles=[role] if role is not None else False,
            users=True,
        )

        try:
            if as_embed:
                embed_obj = make_embed(
                    title=title,
                    description=message,
                    footer=f"Announced by {ctx.author.display_name}",
                )
                if ctx.guild.icon:
                    embed_obj.set_thumbnail(url=ctx.guild.icon.url)

                await channel.send(
                    content=mention_str,
                    embed=embed_obj,
                    allowed_mentions=allowed_mentions,
                )
            else:
                formatted_body = f"## {title}\n\n{message}\n\n*— Posted by {ctx.author.mention}*"
                full_content = f"{mention_str}\n{formatted_body}" if mention_str else formatted_body
                await channel.send(content=full_content, allowed_mentions=allowed_mentions)

            logger.info(
                "announcement_dispatched",
                guild_id=ctx.guild.id,
                channel_id=channel.id,
                author=str(ctx.author),
                ping=normalized_ping,
                as_embed=as_embed,
            )

            confirm = success_embed(
                title="Announcement Delivered",
                description=f"Successfully published announcement to {channel.mention}.",
            )
            await ctx.send(embed=confirm)

        except discord.Forbidden:
            embed = error_embed(
                title="Delivery Failed",
                description=f"I was forbidden from delivering the announcement to {channel.mention}.",
            )
            await ctx.send(embed=embed)
        except discord.HTTPException as err:
            embed = error_embed(
                title="Delivery Error",
                description=f"Failed to deliver announcement: `{err}`",
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="selfroles",
        aliases=["selfrolemenu", "rolesmenu"],
        description="Open the interactive self-assignable role picker",
    )
    @commands.guild_only()
    async def selfroles(self, ctx: Context):
        """Open the interactive self-assignable role picker."""
        role_ids = await self.bot.guild_repo.get_roles(ctx.guild.id, "selfrole")
        if not role_ids:
            embed = info_embed(
                title="No Self-Roles Configured",
                description=(
                    "This server has not configured any self-assignable roles yet.\n"
                    "Server administrators can add roles using `/selfrole add <role>`."
                ),
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        assignable_roles: list[discord.Role] = []
        for rid in sorted(role_ids):
            role = ctx.guild.get_role(rid)
            if role and role < ctx.guild.me.top_role and not role.managed:
                assignable_roles.append(role)

        if not assignable_roles:
            embed = error_embed(
                title="Roles Unavailable",
                description="Configured self-roles are deleted or placed higher than the bot's highest role.",
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        embed = make_embed(
            title="🎭 Self-Assignable Roles",
            description=(
                "Use the menu below to update your roles:\n"
                "• Roles with a checkmark are currently assigned to you.\n"
                "• Unchecking an assigned role will remove it."
            ),
        )
        view = SelfRoleSelectView(roles=assignable_roles, member=ctx.author)
        await ctx.send(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_group(
        name="selfrole",
        description="Manage self-assignable role options for this server",
    )
    @commands.guild_only()
    async def selfrole_group(self, ctx: Context):
        """Manage self-assignable role options for this server."""
        if ctx.invoked_subcommand is None:
            embed = info_embed(
                title="Self-Assignable Roles Configuration",
                description=(
                    "Available commands:\n"
                    "• `/selfrole add <role>`: Add a role to the self-assignable list\n"
                    "• `/selfrole remove <role>`: Remove a role from the self-assignable list\n"
                    "• `/selfrole list`: View all configured self-roles\n"
                    "• `/selfrole post [channel]`: Post a permanent role picker card in a channel\n"
                    "• `/selfroles`: Open the member role picker"
                ),
            )
            await ctx.send(embed=embed)

    @selfrole_group.command(
        name="add",
        description="Add a role to the server's self-assignable roles pool",
    )
    @commands.guild_only()
    @checks.admin_or_permissions(manage_roles=True)
    async def selfrole_add(self, ctx: Context, role: discord.Role):
        """Add a role to the server's self-assignable roles pool."""
        if role.is_default():
            embed = error_embed(
                title="Invalid Role",
                description="The `@everyone` role cannot be made self-assignable.",
            )
            await ctx.send(embed=embed)
            return

        if role.managed:
            embed = error_embed(
                title="Invalid Role",
                description="Managed integration/bot roles cannot be self-assigned.",
            )
            await ctx.send(embed=embed)
            return

        dangerous_perms = (
            "administrator",
            "manage_guild",
            "ban_members",
            "kick_members",
            "manage_roles",
        )
        has_dangerous = any(getattr(role.permissions, perm, False) for perm in dangerous_perms)
        if has_dangerous:
            embed = error_embed(
                title="Security Warning",
                description=(
                    f"Role {role.mention} carries administrative or moderation permissions. "
                    "For server safety, it cannot be configured as a self-assignable role."
                ),
            )
            await ctx.send(embed=embed)
            return

        if role >= ctx.guild.me.top_role:
            embed = error_embed(
                title="Role Hierarchy Error",
                description=f"My highest role must be placed higher than {role.mention} in server settings.",
            )
            await ctx.send(embed=embed)
            return

        if ctx.author != ctx.guild.owner and role >= ctx.author.top_role:
            embed = error_embed(
                title="Role Hierarchy Error",
                description=f"You cannot configure {role.mention} as a self-role because it is higher than or equal to your highest role.",
            )
            await ctx.send(embed=embed)
            return

        await self.bot.guild_repo.add_role(ctx.guild.id, role.id, "selfrole")
        logger.info(
            "selfrole_added", guild_id=ctx.guild.id, role_id=role.id, moderator=str(ctx.author)
        )
        embed = success_embed(
            title="Self-Role Added",
            description=f"Successfully registered {role.mention} as a self-assignable role.",
        )
        await ctx.send(embed=embed)

    @selfrole_group.command(
        name="remove",
        description="Remove a role from the server's self-assignable roles pool",
    )
    @commands.guild_only()
    @checks.admin_or_permissions(manage_roles=True)
    async def selfrole_remove(self, ctx: Context, role: discord.Role):
        """Remove a role from the server's self-assignable roles pool."""
        removed = await self.bot.guild_repo.remove_role(ctx.guild.id, role.id, "selfrole")
        if not removed:
            embed = error_embed(
                title="Role Not Configured",
                description=f"{role.mention} is not currently registered as a self-assignable role.",
            )
            await ctx.send(embed=embed)
            return

        logger.info(
            "selfrole_removed", guild_id=ctx.guild.id, role_id=role.id, moderator=str(ctx.author)
        )
        embed = success_embed(
            title="Self-Role Removed",
            description=f"Successfully removed {role.mention} from self-assignable roles.",
        )
        await ctx.send(embed=embed)

    @selfrole_group.command(
        name="list",
        description="List all self-assignable roles configured on this server",
    )
    @commands.guild_only()
    @checks.mod_or_permissions()
    async def selfrole_list(self, ctx: Context):
        """List all self-assignable roles configured on this server."""
        role_ids = await self.bot.guild_repo.get_roles(ctx.guild.id, "selfrole")
        if not role_ids:
            embed = info_embed(
                title=f"Self-Roles: {ctx.guild.name}",
                description="No self-assignable roles have been configured yet.",
            )
            await ctx.send(embed=embed)
            return

        roles_list: list[str] = []
        for rid in sorted(role_ids):
            role = ctx.guild.get_role(rid)
            if role:
                roles_list.append(f"• {role.mention} (`{role.id}`)")
            else:
                roles_list.append(f"• Deleted Role (`{rid}`)")

        embed = info_embed(
            title=f"Self-Assignable Roles ({len(roles_list)})",
            description="\n".join(roles_list),
        )
        await ctx.send(embed=embed)

    @selfrole_group.command(
        name="post",
        description="Post a permanent self-roles announcement card with an interactive button",
    )
    @commands.guild_only()
    @checks.admin_or_permissions(manage_roles=True)
    async def selfrole_post(
        self,
        ctx: Context,
        channel: discord.TextChannel | None = None,
        *,
        title: str = "🎭 Self-Assignable Roles",
    ):
        """Post a permanent self-roles announcement card with an interactive button."""
        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            embed = error_embed(title="Invalid Channel", description="Must post to a text channel.")
            await ctx.send(embed=embed)
            return

        role_ids = await self.bot.guild_repo.get_roles(ctx.guild.id, "selfrole")
        if not role_ids:
            embed = error_embed(
                title="No Self-Roles Configured",
                description="Configure at least one role with `/selfrole add <role>` before posting the menu.",
            )
            await ctx.send(embed=embed)
            return

        embed = make_embed(
            title=title,
            description=(
                "Click the **Pick Roles** button below to open your personalized role menu.\n"
                "You can select or remove roles at any time."
            ),
        )
        view = PersistentSelfRoleView(self.bot)
        await target_channel.send(embed=embed, view=view)

        confirm = success_embed(
            title="Role Card Posted",
            description=f"Successfully deployed the self-roles card to {target_channel.mention}.",
        )
        await ctx.send(embed=confirm)


async def setup(bot: DiscordBot):
    """Add Moderation commands to cogs"""
    await bot.add_cog(Moderation(bot))
