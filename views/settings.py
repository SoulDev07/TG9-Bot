"""Interactive server settings dashboard with dynamic module toggle buttons."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import discord

from core.embeds import make_embed

if TYPE_CHECKING:
    from bot import DiscordBot


class SettingsDashboardView(discord.ui.View):
    """Dynamic settings dashboard view displaying guild config and module toggle buttons."""

    MODULE_NAMES = ("moderation", "fun", "general")

    def __init__(
        self,
        bot: DiscordBot,
        guild: discord.Guild,
        invoker_id: int,
    ) -> None:
        super().__init__(timeout=300.0)
        self.bot = bot
        self.guild = guild
        self.invoker_id = invoker_id
        self._module_states: dict[str, bool] = {}
        self.message: discord.Message | None = None

    async def initialize(self) -> None:
        """Fetch current module states from database and sync button visuals."""
        for mod in self.MODULE_NAMES:
            self._module_states[mod] = await self.bot.guild_repo.is_module_enabled(
                self.guild.id, mod
            )
        self._update_button_visuals()

    def _update_button_visuals(self) -> None:
        """Update button styles and labels based on current module states."""
        self.clear_items()

        for mod in self.MODULE_NAMES:
            enabled = self._module_states.get(mod, True)
            style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.danger
            label = f"{mod.capitalize()}: {'ON' if enabled else 'OFF'}"
            emoji = "✅" if enabled else "❌"

            button = discord.ui.Button(
                label=label,
                style=style,
                emoji=emoji,
                custom_id=f"toggle_{mod}",
                row=0,
            )
            button.callback = self._create_toggle_callback(mod)
            self.add_item(button)

        refresh_button = discord.ui.Button(
            label="Refresh",
            style=discord.ButtonStyle.secondary,
            emoji="🔄",
            custom_id="refresh_settings",
            row=1,
        )
        refresh_button.callback = self._refresh_callback
        self.add_item(refresh_button)

    def _create_toggle_callback(self, module_name: str):
        """Generate click callback for a specific module toggle button."""

        async def callback(interaction: discord.Interaction) -> None:
            current_state = self._module_states.get(module_name, True)
            new_state = not current_state
            await self.bot.guild_repo.set_module_enabled(self.guild.id, module_name, new_state)
            self._module_states[module_name] = new_state
            self._update_button_visuals()

            embed = await self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

        return callback

    async def _refresh_callback(self, interaction: discord.Interaction) -> None:
        """Reload guild settings and update dashboard visuals."""
        await self.initialize()
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def build_embed(self) -> discord.Embed:
        """Construct the dashboard status embed summarizing settings and module health."""
        settings = await self.bot.guild_repo.get(self.guild.id)
        roles = await self.bot.guild_repo.get_all_roles(self.guild.id)

        prefix = settings.prefix if settings else "!"
        modlog_channel = (
            self.guild.get_channel(settings.modlog_channel_id)
            if settings and settings.modlog_channel_id
            else None
        )
        welcome_channel = (
            self.guild.get_channel(settings.welcome_channel_id)
            if settings and settings.welcome_channel_id
            else None
        )

        admin_role_mentions = [
            self.guild.get_role(rid).mention
            for rid in roles.get("admin", set())
            if self.guild.get_role(rid)
        ]
        mod_role_mentions = [
            self.guild.get_role(rid).mention
            for rid in roles.get("mod", set())
            if self.guild.get_role(rid)
        ]

        module_lines = []
        for mod in self.MODULE_NAMES:
            enabled = self._module_states.get(mod, True)
            status_indicator = "🟢 Enabled" if enabled else "🔴 Disabled"
            module_lines.append(f"• **{mod.capitalize()}**: {status_indicator}")

        return make_embed(
            title=f"Server Settings Dashboard: {self.guild.name}",
            description=(
                "Manage server configuration and toggle modules in real-time.\n"
                "Click the buttons below to enable or disable specific features."
            ),
            fields=[
                ("Command Prefix", f"`{prefix}`", True),
                ("ModLog Channel", modlog_channel.mention if modlog_channel else "None", True),
                (
                    "Welcome Channel",
                    welcome_channel.mention if welcome_channel else "None",
                    True,
                ),
                (
                    "Administrator Roles",
                    ", ".join(admin_role_mentions) if admin_role_mentions else "None configured",
                    False,
                ),
                (
                    "Moderator Roles",
                    ", ".join(mod_role_mentions) if mod_role_mentions else "None configured",
                    False,
                ),
                ("Feature Modules", "\n".join(module_lines), False),
            ],
            footer="TG9 Settings Dashboard • Click toggle buttons to change module states",
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only authorized administrators can interact with settings buttons."""
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "You cannot interact with another administrator's settings dashboard.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        """Disable all dashboard buttons when timeout expires."""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message:
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(view=self)
