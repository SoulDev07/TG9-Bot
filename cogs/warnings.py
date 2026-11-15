"""Tiered warning system, point decay, and automated threshold escalation."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Literal

import discord
import humanize
from discord.ext import commands
from discord.ext.commands import Context

from core import checks, exceptions
from core.embeds import error_embed, info_embed, success_embed
from core.logger import get_logger
from core.time import parse_duration
from services.moderation import warn_member
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


class Warnings(commands.Cog, name="warnings"):
    """Tiered Warnings & Automated Escalation Commands"""

    def __init__(self, bot: DiscordBot):
        self.bot = bot

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
        name="warn",
        aliases=["warning"],
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

    @commands.hybrid_group(
        name="warnings",
        aliases=["warns"],
        description="Inspect and manage member warnings",
    )
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
        message = await ctx.send(embed=embed, view=view if view.total_pages > 1 else None)
        view.message = message

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

    @warnset.group(
        name="action",
        description="Manage automated escalation action thresholds",
    )
    async def warnset_action(self, ctx: Context):
        """Manage automated escalation action thresholds."""
        if ctx.invoked_subcommand is None:
            await self.warnset_action_list(ctx)

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

    @warnset.group(
        name="reason",
        description="Manage preset warning reasons and point weights",
    )
    async def warnset_reason(self, ctx: Context):
        """Manage preset warning reasons and point weights."""
        if ctx.invoked_subcommand is None:
            await self.warnset_reason_list(ctx)

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
    """Register Warnings cog."""
    await bot.add_cog(Warnings(bot))
