"""Interactive pagination view for member warning histories."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import discord

from helpers.embeds import EmbedColor, make_embed

if TYPE_CHECKING:
    from helpers.db.models import WarningRecord


class WarningHistoryPaginationView(discord.ui.View):
    """Paginated view for inspecting a member's active and decayed warnings."""

    def __init__(
        self,
        warnings: list[WarningRecord],
        target_user: discord.User | discord.Member,
        active_points: int,
        invoker_id: int,
        page_size: int = 5,
    ) -> None:
        super().__init__(timeout=180.0)
        self.warnings = warnings
        self.target_user = target_user
        self.active_points = active_points
        self.invoker_id = invoker_id
        self.page_size = page_size
        self.current_page = 0
        self.total_pages = max(1, math.ceil(len(warnings) / page_size))
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
        page_warnings = self.warnings[start:end]

        if not page_warnings:
            return make_embed(
                title=f"Warnings: {self.target_user}",
                description="No warning records found for this user.",
                color=EmbedColor.INFO,
            )

        entries = []
        for w in page_warnings:
            created_ts = int(w.created_at.timestamp())
            status = "🔴 Expired" if w.is_expired else "🟢 Active"
            case_info = f"Case #{w.case_number} | " if w.case_number else ""
            expires_info = (
                f"Expires: <t:{int(w.expires_at.timestamp())}:R>"
                if w.expires_at and not w.is_expired
                else f"Status: {status}"
            )
            pts_label = f"+{w.points} pt{'s' if w.points != 1 else ''}"
            entries.append(
                f"**Warning ID #{w.id}** ({case_info}{pts_label}) • <t:{created_ts}:R>\n"
                f"• **Moderator:** <@{w.moderator_id}>\n"
                f"• **Reason:** {w.reason}\n"
                f"• **{expires_info}**\n"
            )

        content = f"**Active Warning Points:** `{self.active_points}`\n\n" + "\n".join(entries)
        return make_embed(
            title=f"Warning Infractions: {self.target_user}",
            description=content,
            color=EmbedColor.WARNING,
            footer=(
                f"Page {self.current_page + 1} of {self.total_pages} • "
                f"User ID: {self.target_user.id}"
            ),
        )

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary, row=0)
    async def prev_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[WarningHistoryPaginationView],
    ) -> None:
        """Navigate to the previous page."""
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "You are not authorized to use these pagination buttons.",
                ephemeral=True,
            )
            return

        self.current_page = max(0, self.current_page - 1)
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
        button: discord.ui.Button[WarningHistoryPaginationView],
    ) -> None:
        """Display page index label."""
        return

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[WarningHistoryPaginationView],
    ) -> None:
        """Navigate to the next page."""
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "You are not authorized to use these pagination buttons.",
                ephemeral=True,
            )
            return

        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
