"""Stores moderation commands of Bot"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from bot import DiscordBot

logger = get_logger()


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
        description="Warns a user in their private messages",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def warn(
        self,
        ctx: Context,
        member: discord.Member,
        *,
        reason: str = "Not specified",
    ):
        """Warns a user in their private messages."""
        case = await warn_member(ctx, member, reason)
        embed = success_embed(
            title="User Warned!",
            description=f"**{member}** was warned by **{ctx.author}**! (Case #{case.case_number})",
            fields=[("Reason", reason, False)],
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


async def setup(bot: DiscordBot):
    """Add Moderation commands to cogs"""
    await bot.add_cog(Moderation(bot))
