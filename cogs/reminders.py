"""User reminders, timers, and scheduled broadcast messaging."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord
import humanize
from discord.ext import commands, tasks
from discord.ext.commands import Context

from core import checks
from core.db.models import ReminderRecord
from core.embeds import error_embed, info_embed, make_embed, success_embed
from core.logger import get_logger
from core.time import format_duration, parse_duration

if TYPE_CHECKING:
    from bot import DiscordBot

logger = get_logger()


class Reminders(commands.Cog, name="reminders"):
    """User Reminders & Scheduled Broadcasts"""

    def __init__(self, bot: DiscordBot):
        self.bot = bot

    async def cog_load(self) -> None:
        """Start the reminder background worker on cog load."""
        self.reminder_worker.start()

    async def cog_unload(self) -> None:
        """Stop the reminder background worker on cog unload."""
        self.reminder_worker.cancel()

    @tasks.loop(seconds=15.0)
    async def reminder_worker(self) -> None:
        """Check and dispatch expired reminders and recurring schedules concurrently."""
        now = datetime.now(UTC)
        try:
            due_reminders = await self.bot.reminder_repo.get_due_reminders(now)
            if due_reminders:
                await asyncio.gather(
                    *(self._deliver_reminder(reminder, now) for reminder in due_reminders)
                )
        except Exception as e:
            logger.error("reminder_worker_error", error=str(e))

    @reminder_worker.before_loop
    async def before_reminder_worker(self) -> None:
        """Wait until bot cache is ready before polling reminders."""
        await self.bot.wait_until_ready()

    async def _deliver_reminder(self, reminder: ReminderRecord, now: datetime) -> None:
        """Deliver a reminder to the designated channel or direct message."""
        target_channel: discord.TextChannel | discord.Thread | None = None
        guild: discord.Guild | None = None

        if reminder.guild_id:
            guild = self.bot.get_guild(reminder.guild_id)
            if guild and reminder.channel_id:
                chan = guild.get_channel(reminder.channel_id)
                if isinstance(chan, discord.TextChannel | discord.Thread):
                    target_channel = chan

        created_ts = int(reminder.created_at.timestamp())
        embed = make_embed(
            title="⏰ Reminder Alert!",
            description=reminder.message,
            footer=f"Scheduled {humanize.naturaltime(reminder.created_at)}",
            color=0xFEE75C,
        )

        delivered = False

        if target_channel is not None and guild is not None:
            perms = target_channel.permissions_for(guild.me)
            if perms.send_messages and perms.embed_links:
                with contextlib.suppress(discord.HTTPException):
                    await target_channel.send(
                        content=f"🔔 <@{reminder.user_id}>, here is your reminder!",
                        embed=embed,
                    )
                    delivered = True

        if not delivered:
            user = self.bot.get_user(reminder.user_id)
            if user is None:
                with contextlib.suppress(discord.HTTPException):
                    user = await self.bot.fetch_user(reminder.user_id)

            if user:
                with contextlib.suppress(discord.HTTPException):
                    await user.send(
                        content="🔔 Here is your scheduled reminder!",
                        embed=embed,
                    )
                    delivered = True

        if reminder.repeat_interval_seconds and reminder.repeat_interval_seconds >= 60:
            next_time = now + timedelta(seconds=reminder.repeat_interval_seconds)
            assert reminder.id is not None
            await self.bot.reminder_repo.update_remind_at(reminder.id, next_time)
            logger.info(
                "reminder_rescheduled", reminder_id=reminder.id, next_time=next_time.isoformat()
            )
        else:
            assert reminder.id is not None
            await self.bot.reminder_repo.delete_reminder(reminder.id)
            logger.info("reminder_delivered_and_cleared", reminder_id=reminder.id)

    @commands.hybrid_command(
        name="remindme",
        aliases=["remind", "timer"],
        description="Set a personal reminder for a duration from now",
    )
    @discord.app_commands.describe(
        duration="Duration until reminder (e.g. '10m', '2h', '1d', '1w')",
        message="What you want to be reminded about",
        dm="Whether to deliver this reminder via direct message only",
    )
    async def remindme(
        self,
        ctx: Context,
        duration: str,
        *,
        message: str,
        dm: bool = False,
    ):
        """Set a personal reminder with automatic expiration notification."""
        delta = parse_duration(duration)
        if not delta:
            embed = error_embed(
                title="Invalid Duration",
                description=(
                    f"Could not parse `{duration}` as a valid duration.\n"
                    "Examples: `10m`, `30m`, `2h`, `1d`, `3d`, `1w`."
                ),
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        if delta.total_seconds() < 10:
            embed = error_embed(
                title="Duration Too Short",
                description="Reminder duration must be at least 10 seconds.",
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        now = datetime.now(UTC)
        remind_at = now + delta
        remind_ts = int(remind_at.timestamp())

        guild_id = ctx.guild.id if (ctx.guild and not dm) else None
        channel_id = ctx.channel.id if (ctx.guild and not dm) else None

        record = await self.bot.reminder_repo.create_reminder(
            user_id=ctx.author.id,
            guild_id=guild_id,
            channel_id=channel_id,
            message=message,
            remind_at=remind_at,
        )

        delivery_target = "Direct Message" if (dm or not ctx.guild) else ctx.channel.mention
        embed = success_embed(
            title="⏰ Reminder Set!",
            description=(
                f"I will remind you <t:{remind_ts}:R> (<t:{remind_ts}:F>).\n\n"
                f"**Note:** {message}\n"
                f"**Destination:** {delivery_target}"
            ),
            footer=f"Reminder ID: #{record.id} • Use /reminders delete to cancel",
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="remindrepeat",
        aliases=["repeatreminder", "recurring"],
        description="Schedule a repeating reminder or periodic announcement",
    )
    @discord.app_commands.describe(
        interval="Repeating interval (e.g. '1h', '6h', '1d', min: 1m)",
        message="Message content for the recurring broadcast",
        channel="Channel to broadcast in (defaults to current channel)",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(manage_guild=True)
    async def remindrepeat(
        self,
        ctx: Context,
        interval: str,
        *,
        message: str,
        channel: discord.TextChannel | None = None,
    ):
        """Schedule a recurring message broadcast with interval repetition."""
        delta = parse_duration(interval)
        if not delta:
            embed = error_embed(
                title="Invalid Interval",
                description=(
                    f"Could not parse `{interval}` as a valid interval.\n"
                    "Examples: `1h`, `12h`, `1d`, `7d`."
                ),
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        interval_seconds = int(delta.total_seconds())
        if interval_seconds < 60:
            embed = error_embed(
                title="Interval Too Short",
                description="Repeating interval must be at least 1 minute.",
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        target_channel = channel or ctx.channel
        now = datetime.now(UTC)
        first_fire = now + delta
        fire_ts = int(first_fire.timestamp())

        record = await self.bot.reminder_repo.create_reminder(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            channel_id=target_channel.id,
            message=message,
            remind_at=first_fire,
            repeat_interval_seconds=interval_seconds,
        )

        formatted = format_duration(interval_seconds)
        embed = success_embed(
            title="🔁 Recurring Schedule Activated!",
            description=(
                f"Broadcasting to {target_channel.mention} every **{formatted}**.\n\n"
                f"**First Broadcast:** <t:{fire_ts}:R> (<t:{fire_ts}:F>)\n"
                f"**Message:** {message}"
            ),
            footer=f"Schedule ID: #{record.id} • Cancel via /reminders delete {record.id}",
        )
        await ctx.send(embed=embed)

    @commands.hybrid_group(
        name="reminders",
        aliases=["remindlist"],
        description="Inspect and manage your active reminders",
    )
    async def reminders(self, ctx: Context):
        """Inspect and manage your active reminders."""
        if ctx.invoked_subcommand is None:
            await self.reminders_list(ctx)

    @reminders.command(name="list", description="List all your currently pending reminders")
    async def reminders_list(self, ctx: Context):
        """List all your currently pending reminders."""
        user_reminders = await self.bot.reminder_repo.get_user_reminders(ctx.author.id)
        if not user_reminders:
            embed = info_embed(
                title="Your Reminders",
                description=(
                    "You do not have any pending reminders.\n"
                    "Create one with `/remindme <duration> <message>`."
                ),
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        fields: list[tuple[str, str, bool]] = []
        for r in user_reminders[:15]:
            ts = int(r.remind_at.timestamp())
            dest = f"<#{r.channel_id}>" if r.channel_id else "Direct Message"
            repeat_info = (
                f" • 🔁 Every {format_duration(r.repeat_interval_seconds)}"
                if r.repeat_interval_seconds
                else ""
            )
            fields.append(
                (
                    f"Reminder #{r.id} (<t:{ts}:R>)",
                    f"**Note:** {r.message[:100]}\n**Destination:** {dest}{repeat_info}",
                    False,
                )
            )

        embed = make_embed(
            title=f"Pending Reminders ({len(user_reminders)})",
            description="Use `/reminders delete <id>` to cancel any active reminder.",
            fields=fields,
            footer=f"Requested by {ctx.author}",
        )
        await ctx.send(embed=embed, ephemeral=True)

    @reminders.command(name="delete", description="Cancel and remove an active reminder by ID")
    @discord.app_commands.describe(reminder_id="The numeric ID of the reminder to cancel")
    async def reminders_delete(self, ctx: Context, reminder_id: int):
        """Cancel and remove an active reminder by ID."""
        reminder = await self.bot.reminder_repo.get_reminder(reminder_id)
        if not reminder:
            embed = error_embed(
                title="Not Found",
                description=f"Reminder `#{reminder_id}` was not found.",
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        is_owner = self.bot.config.is_owner(ctx.author.id)
        is_creator = reminder.user_id == ctx.author.id
        is_guild_admin = (
            ctx.guild
            and ctx.author.guild_permissions.administrator
            and reminder.guild_id == ctx.guild.id
        )

        if not (is_owner or is_creator or is_guild_admin):
            embed = error_embed(
                title="Permission Denied",
                description="You can only delete reminders you created.",
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        await self.bot.reminder_repo.delete_reminder(reminder_id)
        embed = success_embed(
            title="Reminder Cancelled",
            description=f"Successfully deleted reminder `#{reminder_id}`.",
        )
        await ctx.send(embed=embed)


async def setup(bot: DiscordBot):
    """Register Reminders cog."""
    await bot.add_cog(Reminders(bot))
