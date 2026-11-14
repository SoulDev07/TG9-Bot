"""Interactive server setup wizard UI components using discord.ui."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import discord

from core.embeds import make_embed, success_embed

if TYPE_CHECKING:
    from bot import DiscordBot
    from core.db.models import GuildSettings


class SetupWizardView(discord.ui.View):
    """Interactive onboarding wizard configuring channels and roles with live preview."""

    def __init__(
        self,
        bot: DiscordBot,
        guild: discord.Guild,
        invoker_id: int,
        initial_settings: GuildSettings,
        initial_admin_roles: set[int],
        initial_mod_roles: set[int],
    ) -> None:
        super().__init__(timeout=300.0)
        self.bot = bot
        self.guild = guild
        self.invoker_id = invoker_id

        # Draft selections (seeded with existing database state)
        self.selected_modlog_id: int | None = initial_settings.modlog_channel_id
        self.selected_welcome_id: int | None = initial_settings.welcome_channel_id
        self.selected_admin_role_id: int | None = next(iter(initial_admin_roles), None)
        self.selected_mod_role_id: int | None = next(iter(initial_mod_roles), None)
        self.message: discord.Message | None = None

    def build_embed(self) -> discord.Embed:
        """Construct the live preview embed reflecting current draft selections."""
        modlog_channel = (
            self.guild.get_channel(self.selected_modlog_id) if self.selected_modlog_id else None
        )
        welcome_channel = (
            self.guild.get_channel(self.selected_welcome_id) if self.selected_welcome_id else None
        )
        admin_role = (
            self.guild.get_role(self.selected_admin_role_id)
            if self.selected_admin_role_id
            else None
        )
        mod_role = (
            self.guild.get_role(self.selected_mod_role_id) if self.selected_mod_role_id else None
        )

        modlog_display = modlog_channel.mention if modlog_channel else "*Not configured*"
        welcome_display = welcome_channel.mention if welcome_channel else "*Not configured*"
        admin_display = admin_role.mention if admin_role else "*Not configured*"
        mod_display = mod_role.mention if mod_role else "*Not configured*"

        return make_embed(
            title=f"Server Setup Wizard: {self.guild.name}",
            description=(
                "Configure your server's key channels and authority roles below.\n"
                "Selections update the preview in real-time. Click **Save & Apply** when finished."
            ),
            fields=[
                ("📁 ModLog Channel", modlog_display, True),
                ("👋 Welcome Channel", welcome_display, True),
                ("🛡️ Administrator Role", admin_display, True),
                ("⚔️ Moderator Role", mod_display, True),
            ],
            footer="TG9 Setup Wizard • Changes will not apply until you click Save & Apply",
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the command invoker can interact with this setup session."""
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "You cannot interact with another administrator's setup wizard.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text, discord.ChannelType.news],
        placeholder="Select ModLog audit channel...",
        min_values=1,
        max_values=1,
        row=0,
    )
    async def select_modlog(
        self,
        interaction: discord.Interaction,
        select: discord.ui.ChannelSelect,
    ) -> None:
        """Handle selection of the ModLog audit channel."""
        self.selected_modlog_id = select.values[0].id
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text, discord.ChannelType.news],
        placeholder="Select Welcome announcements channel...",
        min_values=1,
        max_values=1,
        row=1,
    )
    async def select_welcome(
        self,
        interaction: discord.Interaction,
        select: discord.ui.ChannelSelect,
    ) -> None:
        """Handle selection of the Welcome announcements channel."""
        self.selected_welcome_id = select.values[0].id
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Select Administrator role...",
        min_values=1,
        max_values=1,
        row=2,
    )
    async def select_admin_role(
        self,
        interaction: discord.Interaction,
        select: discord.ui.RoleSelect,
    ) -> None:
        """Handle selection of the designated Administrator role."""
        self.selected_admin_role_id = select.values[0].id
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Select Moderator role...",
        min_values=1,
        max_values=1,
        row=3,
    )
    async def select_mod_role(
        self,
        interaction: discord.Interaction,
        select: discord.ui.RoleSelect,
    ) -> None:
        """Handle selection of the designated Moderator role."""
        self.selected_mod_role_id = select.values[0].id
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(
        label="Save & Apply",
        style=discord.ButtonStyle.success,
        emoji="💾",
        row=4,
    )
    async def save_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Persist draft configuration changes to SQLite database."""
        guild_id = self.guild.id

        if self.selected_modlog_id is not None:
            await self.bot.guild_repo.set_modlog_channel(guild_id, self.selected_modlog_id)

        if self.selected_welcome_id is not None:
            await self.bot.guild_repo.set_welcome_channel(guild_id, self.selected_welcome_id)

        if self.selected_admin_role_id is not None:
            await self.bot.guild_repo.add_role(guild_id, self.selected_admin_role_id, "admin")

        if self.selected_mod_role_id is not None:
            await self.bot.guild_repo.add_role(guild_id, self.selected_mod_role_id, "mod")

        # Disable all components upon completion
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True

        confirmation_embed = success_embed(
            title="Configuration Saved!",
            description=(
                f"Successfully updated configuration for **{self.guild.name}**!\n"
                "You can inspect or adjust module toggles anytime using `/settings`."
            ),
        )
        await interaction.response.edit_message(embed=confirmation_embed, view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=4)
    async def cancel_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Cancel wizard session without applying draft changes."""
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True

        cancel_embed = make_embed(
            title="Setup Cancelled",
            description="Wizard session was cancelled. No configuration changes were saved.",
            color=0x808080,
        )
        await interaction.response.edit_message(embed=cancel_embed, view=self)
        self.stop()

    async def on_timeout(self) -> None:
        """Disable all wizard selectors when timeout expires."""
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
        if self.message:
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(view=self)
