"""ModLog case auditing and history search commands."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from discord.ext.commands import Context

from core import checks, exceptions
from core.embeds import error_embed, info_embed, modlog_case_embed, success_embed
from core.logger import get_logger
from services.moderation import edit_case_reason
from views.cases import CaseHistoryPaginationView

if TYPE_CHECKING:
    from bot import DiscordBot

logger = get_logger()


class Cases(commands.Cog, name="cases"):
    """ModLog Case Management & Audit Search"""

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

    @commands.hybrid_group(
        name="case",
        description="Manage and view individual moderation cases",
    )
    @commands.guild_only()
    @checks.mod_or_permissions()
    async def case_group(self, ctx: Context):
        """Manage and view individual moderation cases."""
        if ctx.invoked_subcommand is None:
            embed = info_embed(
                title="ModLog Case Management",
                description=(
                    "Subcommands available:\n"
                    "• `/case view <case_id>`: Look up details of a past moderation case\n"
                    "• `/case edit <case_id> <new_reason>`: Live-edit case reason and audit embed"
                ),
            )
            await ctx.send(embed=embed)

    @case_group.command(name="view", description="Look up details of a past moderation case")
    @commands.guild_only()
    @checks.mod_or_permissions()
    async def case_view(self, ctx: Context, case_id: int):
        """Look up details of a past moderation case."""
        case = await self.bot.case_repo.get_case(ctx.guild.id, case_id)
        if not case:
            await ctx.send(
                embed=error_embed(description=f"Case #{case_id} was not found for this server.")
            )
            return

        target = ctx.guild.get_member(case.user_id)
        if not target:
            with contextlib.suppress(discord.HTTPException):
                target = await self.bot.fetch_user(case.user_id)

        mod = ctx.guild.get_member(case.moderator_id)
        if not mod:
            with contextlib.suppress(discord.HTTPException):
                mod = await self.bot.fetch_user(case.moderator_id)

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
        cases = await self.bot.case_repo.get_cases_for_user(ctx.guild.id, member.id)
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
        message = await ctx.send(embed=embed, view=view if view.total_pages > 1 else None)
        view.message = message


async def setup(bot: DiscordBot):
    """Register Cases cog."""
    await bot.add_cog(Cases(bot))
