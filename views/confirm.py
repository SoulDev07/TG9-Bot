"""Reusable interactive confirmation view for high-impact actions."""

from __future__ import annotations

import discord


class ConfirmView(discord.ui.View):
    """Interactive confirmation dialog with Confirm and Cancel action buttons."""

    def __init__(
        self,
        invoker_id: int,
        confirm_label: str = "Confirm",
        cancel_label: str = "Cancel",
        confirm_style: discord.ButtonStyle = discord.ButtonStyle.danger,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.invoker_id = invoker_id
        self.value: bool | None = None

        self.confirm_button.label = confirm_label
        self.confirm_button.style = confirm_style
        self.cancel_button.label = cancel_label

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the command invoker can confirm or cancel the action."""
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "You cannot interact with another moderator's confirmation prompt.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji="⚠️", row=0)
    async def confirm_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Handle confirmation."""
        self.value = True
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=0)
    async def cancel_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Handle cancellation."""
        self.value = False
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_timeout(self) -> None:
        """Disable buttons upon interaction timeout."""
        self.value = False
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
