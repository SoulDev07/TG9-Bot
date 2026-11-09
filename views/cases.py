"""Interactive pagination view for moderation case histories."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import discord

from helpers.embeds import EmbedColor, make_embed

if TYPE_CHECKING:
    from helpers.db.models import ModCase


class CaseHistoryPaginationView(discord.ui.View):
    """Paginated view for browsing a member's moderation infractions history."""

    def __init__(
        self,
        cases: list[ModCase],
        target_user: discord.User | discord.Member,
        invoker_id: int,
        page_size: int = 5,
    ) -> None:
        super().__init__(timeout=180.0)
        self.cases = cases
        self.target_user = target_user
        self.invoker_id = invoker_id
        self.page_size = page_size
        self.current_page = 0
        self.total_pages = max(1, math.ceil(len(cases) / page_size))
        self._update_buttons()

    def _update_buttons(self) -> None:
        """Update button enabled states and label counter."""
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1
        self.page_counter.label = f"Page {self.current_page + 1} of {self.total_pages}"

    def build_embed(self) -> discord.Embed:
        """Construct the embed for the active page."""
        start = self.current_page * self.page_size
        end = start + self.page_size
        page_cases = self.cases[start:end]

        if not page_cases:
            return make_embed(
                title=f"Moderation History: {self.target_user}",
                description="No moderation cases recorded for this user.",
                color=EmbedColor.INFO,
            )

        entries = []
        for case in page_cases:
            timestamp_sec = int(case.created_at.timestamp())
            entries.append(
                f"**Case #{case.case_number} | {case.action.upper()}** • <t:{timestamp_sec}:R>\n"
                f"• **Moderator:** <@{case.moderator_id}>\n"
                f"• **Reason:** {case.reason}\n"
            )

        return make_embed(
            title=f"Moderation History: {self.target_user} ({len(self.cases)} total)",
            description="\n".join(entries),
            color=EmbedColor.WARNING,
            footer=(
                f"Page {self.current_page + 1} of {self.total_pages} • "
                f"User ID: {self.target_user.id}"
            ),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the moderator who requested history can paginate."""
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "You cannot control pagination on another moderator's query.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def prev_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Navigate to the previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(
        label="Page 1 of 1",
        style=discord.ButtonStyle.secondary,
        disabled=True,
        row=0,
    )
    async def page_counter(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Visual display counter (non-interactive)."""

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Navigate to the next page."""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_timeout(self) -> None:
        """Disable buttons upon interaction timeout."""
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
