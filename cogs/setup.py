"""Server setup wizard and settings dashboard commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands
from discord.ext.commands import Context

from core import checks
from views.settings import SettingsDashboardView
from views.setup import SetupWizardView

if TYPE_CHECKING:
    from bot import DiscordBot


class Setup(commands.Cog, name="setup"):
    """Server Configuration & Interactive UI Setup"""

    def __init__(self, bot: DiscordBot):
        self.bot = bot

    @commands.hybrid_command(
        name="setup",
        description="Launch the interactive server onboarding setup wizard",
    )
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def setup(self, ctx: Context):
        """Launch the interactive setup wizard with channel and role pickers."""
        assert ctx.guild is not None

        settings = await self.bot.guild_repo.get_or_create(
            ctx.guild.id,
            default_prefix=self.bot.config.prefix,
        )
        admin_roles = await self.bot.guild_repo.get_roles(ctx.guild.id, "admin")
        mod_roles = await self.bot.guild_repo.get_roles(ctx.guild.id, "mod")

        view = SetupWizardView(
            bot=self.bot,
            guild=ctx.guild,
            invoker_id=ctx.author.id,
            initial_settings=settings,
            initial_admin_roles=admin_roles,
            initial_mod_roles=mod_roles,
        )
        embed = view.build_embed()
        await ctx.send(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_command(
        name="settings",
        description="Open the interactive server configuration and module dashboard",
    )
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def settings(self, ctx: Context):
        """Open the interactive settings dashboard with dynamic module toggle buttons."""
        assert ctx.guild is not None

        view = SettingsDashboardView(
            bot=self.bot,
            guild=ctx.guild,
            invoker_id=ctx.author.id,
        )
        await view.initialize()
        embed = await view.build_embed()
        await ctx.send(embed=embed, view=view, ephemeral=True)


async def setup(bot: DiscordBot):
    """Register Setup cog."""
    await bot.add_cog(Setup(bot))
