"""Stores moderation commands of Bot"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

import discord
import humanize
from discord.ext import commands, tasks
from discord.ext.commands import Context

from helpers import checks, exceptions
from helpers.embeds import (
    EmbedColor,
    error_embed,
    info_embed,
    make_embed,
    modlog_case_embed,
    success_embed,
)
from helpers.logger import get_logger
from helpers.time import parse_duration
from services.moderation import (
    ban_member,
    edit_case_reason,
    hackban_user,
    kick_member,
    massban_users,
    purge_channel,
    softban_member,
    tempban_member,
    unban_member,
    warn_member,
)
from views.cases import CaseHistoryPaginationView
from views.confirm import ConfirmView
from views.warnings import WarningHistoryPaginationView

if TYPE_CHECKING:
    from bot import DiscordBot

logger = get_logger()


async def warning_reason_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[discord.app_commands.Choice[str]]:
    """Suggest configured warning reason templates dynamically."""
    if not interaction.guild:
        return []
    reasons = await interaction.client.warning_repo.get_reasons(interaction.guild.id)
    choices = [
        discord.app_commands.Choice(
            name=f"{r.name.title()} ({r.points} pt{'s' if r.points != 1 else ''})",
            value=r.name,
        )
        for r in reasons
        if current.lower() in r.name.lower()
    ]
    return choices[:25]


class Moderation(commands.Cog, name="moderation"):
    """Moderation Commands"""

    def __init__(self, bot: DiscordBot):
        self.bot = bot

    async def cog_load(self) -> None:
        """Start the background tempban worker upon cog loading."""
        if not self.check_tempbans_task.is_running():
            self.check_tempbans_task.start()

    async def cog_unload(self) -> None:
        """Cancel background tempban worker when cog is unloaded."""
        if self.check_tempbans_task.is_running():
            self.check_tempbans_task.cancel()

    @tasks.loop(seconds=30.0)
    async def check_tempbans_task(self) -> None:
        """Periodic background worker checking and unbanning expired tempbans."""
        now = datetime.now(UTC)
        expired = await self.bot.tempban_repo.get_expired_tempbans(now)
        for guild_id, user_id, reason in expired:
            guild = self.bot.get_guild(guild_id)
            if not guild or not guild.me.guild_permissions.ban_members:
                continue

            with contextlib.suppress(discord.NotFound, discord.Forbidden, discord.HTTPException):
                await guild.unban(discord.Object(id=user_id), reason=f"Tempban expired: {reason}")
            await self.bot.tempban_repo.remove_tempban(guild_id, user_id)
            logger.info("tempban_expired_unbanned", guild_id=guild_id, user_id=user_id)

    @check_tempbans_task.before_loop
    async def before_check_tempbans(self) -> None:
        """Wait until bot cache is ready before checking expirations."""
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
        name="warn",
        description="Warns a user with optional points and automated threshold escalation",
    )
    @discord.app_commands.describe(
        member="The member to issue a warning to",
        reason="Reason for the warning or preset category name",
        points="Custom point weight (defaults to preset value or 1)",
    )
    @discord.app_commands.autocomplete(reason=warning_reason_autocomplete)
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def warn(
        self,
        ctx: Context,
        member: discord.Member,
        points: int | None = None,
        *,
        reason: str = "Not specified",
    ):
        """Warns a member with points, applying automated threshold escalations."""
        case, warning_record, new_points, escalated_action = await warn_member(
            ctx, member, reason=reason, points=points
        )

        fields: list[tuple[str, str, bool]] = [
            ("Reason", reason, False),
            ("Points", f"+{warning_record.points} (Total Active: {new_points})", True),
        ]
        if warning_record.expires_at:
            exp_ts = int(warning_record.expires_at.timestamp())
            fields.append(("Expires", f"<t:{exp_ts}:R>", True))
        else:
            fields.append(("Expires", "Never", True))

        if escalated_action:
            action_name = escalated_action.action.upper()
            if escalated_action.action == "timeout":
                dur = humanize.precisedelta(
                    timedelta(seconds=escalated_action.duration_seconds or 3600)
                )
                action_name += f" ({dur})"
            fields.append(
                (
                    "⚠️ Automated Escalation",
                    f"Threshold reached ({escalated_action.points} pts): **{action_name}**",
                    False,
                )
            )

        embed = success_embed(
            title="User Warned!",
            description=f"**{member}** was warned by **{ctx.author}**! (Case #{case.case_number})",
            fields=fields,
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
        except discord.Forbidden:
            embed = error_embed(
                description=(
                    f"An error occurred while trying to kick {member.mention}. "
                    "Make sure my role is placed higher than the target user's role."
                )
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="ban", description="Ban a user from the server")
    @commands.guild_only()
    @checks.mod_or_permissions(ban_members=True)
    async def ban(
        self,
        ctx: Context,
        member: discord.Member,
        *,
        reason: str = "Not specified",
    ):
        """Ban a user from the server."""
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
        except discord.Forbidden:
            embed = error_embed(
                description=(
                    f"An error occurred while trying to ban {member.mention}. "
                    "Make sure my role is placed higher than the target user's role."
                )
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="softban",
        description="Ban and immediately unban a user to purge their recent messages",
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
        """Ban and immediately unban a user to purge recent messages without keeping them banned."""
        clean_days = max(1, min(7, days))
        case = await softban_member(ctx, member, days=clean_days, reason=reason)
        embed = success_embed(
            title="User Softbanned!",
            description=(
                f"**{member}** was softbanned by **{ctx.author}**! (Case #{case.case_number})"
            ),
            fields=[
                ("Purged History", f"{clean_days} day(s)", True),
                ("Reason", reason, False),
            ],
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="tempban",
        description="Temporarily ban a user for a duration (e.g., 1d, 12h, 30m)",
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
        """Temporarily ban a user with automated expiration."""
        delta = parse_duration(duration)
        if not delta:
            embed = error_embed(
                description=f"Invalid duration format `{duration}`. Use e.g. `1d`, `12h`, `30m`."
            )
            await ctx.send(embed=embed)
            return

        case = await tempban_member(ctx, member, duration=delta, reason=reason)
        embed = success_embed(
            title="User Tempbanned!",
            description=(
                f"**{member}** was temporarily banned by **{ctx.author}**! "
                f"(Case #{case.case_number})"
            ),
            fields=[
                ("Duration", humanize.naturaldelta(delta), True),
                ("Reason", reason, False),
            ],
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="hackban",
        aliases=["preban"],
        description="Ban a user ID pre-emptively before they join the server",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(ban_members=True)
    async def hackban(
        self,
        ctx: Context,
        user_id: str,
        *,
        reason: str = "Not specified",
    ):
        """Pre-emptively ban a malicious user ID."""
        clean_id = user_id.strip()
        if not clean_id.isdigit():
            embed = error_embed(description=f"Invalid user ID `{user_id}`. Must be numeric.")
            await ctx.send(embed=embed)
            return

        uid = int(clean_id)
        case = await hackban_user(ctx, uid, reason=reason)
        embed = success_embed(
            title="User Pre-banned!",
            description=(
                f"User ID `{uid}` was banned by **{ctx.author}**! (Case #{case.case_number})"
            ),
            fields=[("Reason", reason, False)],
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="unban",
        description="Unban a user from the server with optional one-time reinvite link",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(ban_members=True)
    async def unban(
        self,
        ctx: Context,
        user: discord.User,
        reinvite: bool = False,
        *,
        reason: str = "Not specified",
    ):
        """Unban a user with optional automatic reinvite link generation."""
        case, invite_url = await unban_member(ctx, user, reinvite=reinvite, reason=reason)
        fields: list[tuple[str, str, bool]] = [("Reason", reason, False)]
        if reinvite:
            status = f"[Invite Link]({invite_url})" if invite_url else "DM Failed / Unavailable"
            fields.append(("Reinvite Link", status, True))

        embed = success_embed(
            title="User Unbanned!",
            description=f"**{user}** was unbanned by **{ctx.author}**! (Case #{case.case_number})",
            fields=fields,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="massban",
        description="Ban multiple user IDs in bulk with interactive confirmation",
    )
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def massban(
        self,
        ctx: Context,
        user_ids: str,
        *,
        reason: str = "Not specified",
    ):
        """Ban multiple user IDs with an interactive confirmation guard."""
        raw_tokens = [tok.strip(",") for tok in user_ids.split()]
        valid_uids: list[int] = [int(tok) for tok in raw_tokens if tok.isdigit()]

        if not valid_uids:
            embed = error_embed(description="No valid user IDs found in input.")
            await ctx.send(embed=embed)
            return

        view = ConfirmView(
            invoker_id=ctx.author.id,
            confirm_label=f"Ban {len(valid_uids)} Users",
        )
        confirm_embed = make_embed(
            title="Confirm Massban",
            description=(
                f"Are you sure you want to ban **{len(valid_uids)}** user(s)?\n"
                f"**Reason:** {reason}\n\n"
                "This action will ban each user from the server."
            ),
            color=EmbedColor.ERROR,
        )
        prompt_msg = await ctx.send(embed=confirm_embed, view=view)
        await view.wait()

        if not view.value:
            cancel_embed = make_embed(
                title="Massban Cancelled",
                description="Massban operation was cancelled. No users were banned.",
                color=0x808080,
            )
            await prompt_msg.edit(embed=cancel_embed, view=None)
            return

        banned, failed = await massban_users(ctx, valid_uids, reason=reason)
        banned_preview = ", ".join(str(u) for u in banned[:15])
        if len(banned) > 15:
            banned_preview += f" ... (+{len(banned) - 15} more)"

        result_embed = success_embed(
            title="Massban Completed",
            description=f"Successfully banned **{len(banned)}** users. Failed: **{len(failed)}**.",
            fields=[
                ("Banned IDs", f"`{banned_preview}`" if banned else "None", False),
                ("Reason", reason, False),
            ],
        )
        await prompt_msg.edit(embed=result_embed, view=None)

    @commands.hybrid_command(name="purge", description="Delete a number of messages")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def purge(self, ctx: Context, amount: int):
        """Delete a number of messages."""
        if amount < 1:
            embed = error_embed(
                description=f"`{amount}` is not a valid number. Must be at least 1."
            )
            await ctx.send(embed=embed)
            return

        purged_count = await purge_channel(ctx.channel, amount)
        embed = success_embed(
            title="Chat Cleared!",
            description=f"**{ctx.author}** cleared **{purged_count}** messages!",
        )
        await ctx.send(embed=embed, delete_after=5)

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
                    "Configure administrative and moderator roles for this server:\n"
                    "• `/roles addadmin <role>`: Designate an Administrator role\n"
                    "• `/roles removeadmin <role>`: Remove an Administrator role\n"
                    "• `/roles addmod <role>`: Designate a Moderator role\n"
                    "• `/roles removemod <role>`: Remove a Moderator role\n"
                    "• `/roles list`: List all configured roles"
                ),
            )
            await ctx.send(embed=embed)

    @roles.command(name="addadmin", description="Designate an administrator role")
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def add_admin_role(self, ctx: Context, role: discord.Role):
        """Designate an administrator role for this server."""
        await self.bot.guild_repo.add_role(ctx.guild.id, role.id, "admin")
        embed = success_embed(
            title="Role Updated",
            description=f"Successfully added {role.mention} as an **Administrator** role.",
        )
        await ctx.send(embed=embed)

    @roles.command(name="removeadmin", description="Remove a designated administrator role")
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def remove_admin_role(self, ctx: Context, role: discord.Role):
        """Remove a designated administrator role from this server."""
        removed = await self.bot.guild_repo.remove_role(ctx.guild.id, role.id, "admin")
        if not removed:
            embed = error_embed(
                title="Error",
                description=f"{role.mention} is not registered as an Administrator role.",
            )
            await ctx.send(embed=embed)
            return
        embed = success_embed(
            title="Role Removed",
            description=f"Successfully removed {role.mention} from Administrator roles.",
        )
        await ctx.send(embed=embed)

    @roles.command(name="addmod", description="Designate a moderator role")
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def add_mod_role(self, ctx: Context, role: discord.Role):
        """Designate a moderator role for this server."""
        await self.bot.guild_repo.add_role(ctx.guild.id, role.id, "mod")
        embed = success_embed(
            title="Role Updated",
            description=f"Successfully added {role.mention} as a **Moderator** role.",
        )
        await ctx.send(embed=embed)

    @roles.command(name="removemod", description="Remove a designated moderator role")
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def remove_mod_role(self, ctx: Context, role: discord.Role):
        """Remove a designated moderator role from this server."""
        removed = await self.bot.guild_repo.remove_role(ctx.guild.id, role.id, "mod")
        if not removed:
            embed = error_embed(
                title="Error",
                description=f"{role.mention} is not registered as a Moderator role.",
            )
            await ctx.send(embed=embed)
            return
        embed = success_embed(
            title="Role Removed",
            description=f"Successfully removed {role.mention} from Moderator roles.",
        )
        await ctx.send(embed=embed)

    @roles.command(name="list", description="List configured administrator and moderator roles")
    @commands.guild_only()
    @checks.mod_or_permissions()
    async def list_roles(self, ctx: Context):
        """List configured administrator and moderator roles for this server."""
        roles_data = await self.bot.guild_repo.get_all_roles(ctx.guild.id)
        admin_roles = [
            ctx.guild.get_role(rid).mention
            for rid in roles_data.get("admin", set())
            if ctx.guild.get_role(rid)
        ]
        mod_roles = [
            ctx.guild.get_role(rid).mention
            for rid in roles_data.get("mod", set())
            if ctx.guild.get_role(rid)
        ]

        embed = make_embed(
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

    @commands.hybrid_group(name="case", description="Manage and view individual moderation cases")
    @commands.guild_only()
    @checks.mod_or_permissions()
    async def case_group(self, ctx: Context):
        """Manage and view individual moderation cases."""
        if ctx.invoked_subcommand is None:
            embed = info_embed(
                title="Case Management",
                description=(
                    "Manage recorded moderation cases:\n"
                    "• `/case view <case_id>`: View details and reason of a case\n"
                    "• `/case edit <case_id> <reason>`: Update reason and live-edit log\n"
                    "• `/cases user <target_member>`: View full infraction history"
                ),
            )
            await ctx.send(embed=embed)

    @case_group.command(name="view", description="Lookup and display historical infraction details")
    @commands.guild_only()
    @checks.mod_or_permissions()
    async def case_view(self, ctx: Context, case_id: int):
        """Lookup and display historical infraction details for a specific case."""
        case = await self.bot.mod_case_repo.get_case(ctx.guild.id, case_id)
        if not case:
            await ctx.send(
                embed=error_embed(description=f"Case #{case_id} was not found for this server.")
            )
            return

        target = ctx.guild.get_member(case.user_id) or await self.bot.fetch_user(case.user_id)
        mod = ctx.guild.get_member(case.moderator_id) or await self.bot.fetch_user(
            case.moderator_id
        )

        embed = modlog_case_embed(case, user=target, moderator=mod)
        await ctx.send(embed=embed)

    @case_group.command(
        name="edit",
        description="Update the reason for a moderation case and edit its live audit log",
    )
    @commands.guild_only()
    @checks.mod_or_permissions()
    async def case_edit(self, ctx: Context, case_id: int, *, new_reason: str):
        """Update the reason for a moderation case and edit its live audit log."""
        success, message, _ = await edit_case_reason(ctx, case_id, new_reason=new_reason)
        if success:
            await ctx.send(
                embed=success_embed(
                    title="Case Updated",
                    description=message,
                    fields=[("New Reason", new_reason, False)],
                )
            )
        else:
            await ctx.send(embed=error_embed(description=message))

    @commands.hybrid_group(name="cases", description="Search and view member moderation history")
    @commands.guild_only()
    @checks.mod_or_permissions()
    async def cases_group(self, ctx: Context):
        """Search and view member moderation history."""
        if ctx.invoked_subcommand is None:
            embed = info_embed(
                title="Moderation Case Search",
                description="Use `/cases user <target_member>` to view all recorded infractions.",
            )
            await ctx.send(embed=embed)

    @cases_group.command(
        name="user",
        description="Shows warning, kick, and ban history for a specific member",
    )
    @commands.guild_only()
    @checks.mod_or_permissions()
    async def cases_user(self, ctx: Context, member: discord.Member | discord.User):
        """Shows warning, kick, and ban history for a specific member with pagination."""
        cases = await self.bot.mod_case_repo.get_cases_for_user(ctx.guild.id, member.id)
        if not cases:
            await ctx.send(
                embed=info_embed(
                    title=f"Moderation History: {member}",
                    description=f"No moderation cases recorded for {member.mention}.",
                )
            )
            return

        view = CaseHistoryPaginationView(
            cases=cases,
            target_user=member,
            invoker_id=ctx.author.id,
            page_size=5,
        )
        embed = view.build_embed()
        await ctx.send(embed=embed, view=view if view.total_pages > 1 else None)

    @commands.hybrid_group(name="warnings", description="Inspect and manage member warnings")
    @commands.guild_only()
    @checks.mod_or_permissions()
    async def warnings(self, ctx: Context):
        """Inspect and manage member warnings and point totals."""
        if ctx.invoked_subcommand is None:
            embed = info_embed(
                title="Warning Management",
                description=(
                    "Subcommands available:\n"
                    "• `/warnings user <member>`: View all warning infractions for a member\n"
                    "• `/warnings delete <warning_id>`: Pardon or delete a warning record"
                ),
            )
            await ctx.send(embed=embed)

    @warnings.command(
        name="user",
        description="View active and expired warning infractions for a member",
    )
    @discord.app_commands.describe(member="The member whose warnings to inspect")
    @commands.guild_only()
    @checks.mod_or_permissions()
    async def warnings_user(self, ctx: Context, member: discord.Member):
        """View active and expired warning infractions for a member with pagination."""
        user_warnings = await self.bot.warning_repo.get_warnings(ctx.guild.id, member.id)
        if not user_warnings:
            await ctx.send(
                embed=info_embed(
                    title=f"Warnings: {member}",
                    description=f"{member.mention} has no recorded warnings.",
                )
            )
            return

        active_points = await self.bot.warning_repo.get_active_points(ctx.guild.id, member.id)
        view = WarningHistoryPaginationView(
            warnings=user_warnings,
            target_user=member,
            active_points=active_points,
            invoker_id=ctx.author.id,
            page_size=5,
        )
        embed = view.build_embed()
        await ctx.send(embed=embed, view=view if view.total_pages > 1 else None)

    @warnings.command(
        name="delete",
        description="Pardon or remove a specific warning record by ID",
    )
    @discord.app_commands.describe(warning_id="The numeric ID of the warning to pardon")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def warnings_delete(self, ctx: Context, warning_id: int):
        """Pardon or remove a specific warning record by ID."""
        deleted = await self.bot.warning_repo.delete_warning(ctx.guild.id, warning_id)
        if not deleted:
            await ctx.send(
                embed=error_embed(
                    description=f"Warning ID `#{warning_id}` was not found for this server."
                )
            )
            return

        await ctx.send(
            embed=success_embed(
                title="Warning Removed",
                description=f"Successfully removed warning `#{warning_id}`.",
            )
        )

    @commands.hybrid_group(
        name="warnset",
        description="Configure warning rules, reasons, and automated escalations",
    )
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def warnset(self, ctx: Context):
        """Configure warning rules, reasons, and automated action thresholds."""
        if ctx.invoked_subcommand is None:
            settings = await self.bot.warning_repo.get_settings(ctx.guild.id)
            decay_desc = (
                f"{settings.decay_days} days" if settings.decay_days > 0 else "Never (Permanent)"
            )
            embed = info_embed(
                title="Warning System Configuration",
                description=(
                    f"**Point Decay Interval:** `{decay_desc}`\n\n"
                    "**Available Commands:**\n"
                    "• `/warnset decay <days>`: Set points expiration period (0 for permanent)\n"
                    "• `/warnset action list`: View all action thresholds\n"
                    "• `/warnset action set <pts> <action> [dur]`: Configure an action threshold\n"
                    "• `/warnset action delete <pts>`: Delete an action threshold\n"
                    "• `/warnset reason list`: View configured warning reasons\n"
                    "• `/warnset reason set <name> <pts> [desc]`: Configure a reason preset\n"
                    "• `/warnset reason delete <name>`: Delete a reason preset"
                ),
            )
            await ctx.send(embed=embed)

    @warnset.command(
        name="decay",
        description="Configure warning points decay period in days (0 disables decay)",
    )
    @discord.app_commands.describe(
        days="Number of days before warning points expire (0 to never expire)"
    )
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def warnset_decay(self, ctx: Context, days: int):
        """Configure warning points decay period in days."""
        if days < 0:
            await ctx.send(embed=error_embed(description="Decay days cannot be negative."))
            return

        await self.bot.warning_repo.set_decay(ctx.guild.id, days)
        decay_desc = (
            f"Warning points will now expire after **{days} days**."
            if days > 0
            else "Warning points will **never expire**."
        )
        await ctx.send(
            embed=success_embed(
                title="Warning Decay Updated",
                description=decay_desc,
            )
        )

    warnset_action = warnset.group(
        name="action",
        description="Manage automated escalation action thresholds",
    )

    @warnset_action.command(
        name="list",
        description="List all configured escalation action thresholds",
    )
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def warnset_action_list(self, ctx: Context):
        """List all configured escalation action thresholds."""
        actions = await self.bot.warning_repo.get_actions(ctx.guild.id)
        entries = []
        for a in actions:
            action_desc = a.action.upper()
            if a.action == "timeout":
                dur = humanize.precisedelta(timedelta(seconds=a.duration_seconds or 3600))
                action_desc += f" ({dur})"
            entries.append(f"• **{a.points} points** ➜ **{action_desc}**")

        embed = info_embed(
            title=f"Warning Action Thresholds: {ctx.guild.name}",
            description="\n".join(entries) if entries else "No action thresholds configured.",
        )
        await ctx.send(embed=embed)

    @warnset_action.command(
        name="set",
        description="Configure an automated escalation action at a point threshold",
    )
    @discord.app_commands.describe(
        points="Points required to trigger action (e.g., 3, 5, 10)",
        action="Action to execute: timeout, kick, ban, softban",
        duration="Duration for timeout (e.g., 1h, 30m, 1d)",
    )
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def warnset_action_set(
        self,
        ctx: Context,
        points: int,
        action: Literal["timeout", "kick", "ban", "softban"],
        duration: str | None = None,
    ):
        """Configure an automated escalation action at a point threshold."""
        if points < 1:
            await ctx.send(embed=error_embed(description="Point threshold must be at least 1."))
            return

        duration_seconds: int | None = None
        if action == "timeout":
            if duration:
                parsed = parse_duration(duration)
                if not parsed:
                    await ctx.send(
                        embed=error_embed(
                            description=(
                                f"Invalid duration format: `{duration}`. "
                                "Examples: `30m`, `1h`, `1d`."
                            )
                        )
                    )
                    return
                duration_seconds = int(parsed.total_seconds())
            else:
                duration_seconds = 3600

        await self.bot.warning_repo.set_action(
            ctx.guild.id,
            points=points,
            action=action,
            duration_seconds=duration_seconds,
        )

        action_display = action.upper()
        if duration_seconds:
            action_display += f" ({humanize.precisedelta(timedelta(seconds=duration_seconds))})"

        await ctx.send(
            embed=success_embed(
                title="Action Threshold Configured",
                description=(
                    f"Reaching **{points} points** will automatically "
                    f"execute: **{action_display}**."
                ),
            )
        )

    @warnset_action.command(
        name="delete",
        description="Remove an escalation action threshold by point value",
    )
    @discord.app_commands.describe(points="Point threshold to remove")
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def warnset_action_delete(self, ctx: Context, points: int):
        """Remove an escalation action threshold by point value."""
        deleted = await self.bot.warning_repo.delete_action(ctx.guild.id, points)
        if not deleted:
            await ctx.send(
                embed=error_embed(
                    description=f"No action threshold found configured at `{points}` points."
                )
            )
            return

        await ctx.send(
            embed=success_embed(
                title="Threshold Removed",
                description=f"Successfully removed escalation threshold at `{points}` points.",
            )
        )

    warnset_reason = warnset.group(
        name="reason",
        description="Manage preset warning reasons and point weights",
    )

    @warnset_reason.command(
        name="list",
        description="List all configured warning reasons and their point values",
    )
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def warnset_reason_list(self, ctx: Context):
        """List all configured warning reasons and their point values."""
        reasons = await self.bot.warning_repo.get_reasons(ctx.guild.id)
        entries = []
        for r in reasons:
            desc_part = f" - *{r.description}*" if r.description else ""
            entries.append(
                f"• **{r.name.title()}**: `{r.points} pt{'s' if r.points != 1 else ''}`{desc_part}"
            )

        embed = info_embed(
            title=f"Warning Reasons: {ctx.guild.name}",
            description="\n".join(entries) if entries else "No preset warning reasons configured.",
        )
        await ctx.send(embed=embed)

    @warnset_reason.command(
        name="set",
        description="Create or update a preset warning reason with assigned point value",
    )
    @discord.app_commands.describe(
        name="Preset name (e.g. spam, toxicity, nsfw)",
        points="Points assigned to this infraction (at least 1)",
        description="Optional brief explanation of the infraction rule",
    )
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def warnset_reason_set(
        self,
        ctx: Context,
        name: str,
        points: int,
        *,
        description: str | None = None,
    ):
        """Create or update a preset warning reason with assigned point value."""
        if points < 1:
            await ctx.send(embed=error_embed(description="Points must be at least 1."))
            return

        await self.bot.warning_repo.set_reason(
            ctx.guild.id,
            name=name,
            points=points,
            description=description,
        )
        await ctx.send(
            embed=success_embed(
                title="Reason Preset Configured",
                description=(
                    f"Configured reason **{name.title()}** with **{points} "
                    f"point{'s' if points != 1 else ''}**."
                ),
            )
        )

    @warnset_reason.command(
        name="delete",
        description="Delete a configured preset warning reason",
    )
    @discord.app_commands.describe(name="Name of the reason preset to delete")
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def warnset_reason_delete(self, ctx: Context, name: str):
        """Delete a configured preset warning reason."""
        deleted = await self.bot.warning_repo.delete_reason(ctx.guild.id, name)
        if not deleted:
            await ctx.send(
                embed=error_embed(
                    description=f"Reason preset `{name}` was not found for this server."
                )
            )
            return

        await ctx.send(
            embed=success_embed(
                title="Reason Deleted",
                description=f"Successfully removed warning reason preset `{name}`.",
            )
        )


async def setup(bot: DiscordBot):
    """Add Moderation commands to cogs"""
    await bot.add_cog(Moderation(bot))
