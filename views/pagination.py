"""Generic reusable pagination view utilizing Python 3.12 type parameters."""

from __future__ import annotations

import math
from typing import override

import discord


class BasePaginationView[T](discord.ui.View):
    """Generic interactive pagination view for sequences of items."""

    def __init__(
        self,
        items: list[T],
        invoker_id: int,
        page_size: int = 5,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.items = items
        self.invoker_id = invoker_id
        self.page_size = page_size
        self.current_page = 0
        self.total_pages = max(1, math.ceil(len(items) / page_size))
        self._update_buttons()

    def _update_buttons(self) -> None:
        """Update button enabled states and label counter."""
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1
        self.page_counter.label = f"Page {self.current_page + 1} of {self.total_pages}"

    def get_current_page_items(self) -> list[T]:
        """Slice and return the items belonging to the active page."""
        start = self.current_page * self.page_size
        return self.items[start : start + self.page_size]

    def build_embed(self) -> discord.Embed:
        """Construct the embed for the active page. Must be overridden by subclasses."""
        raise NotImplementedError("Subclasses must implement build_embed")

    @override
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Enforce that only the command invoker can click pagination controls."""
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "You are not authorized to use these pagination buttons.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary, row=0)
    async def prev_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Navigate to the previous page."""
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
        button: discord.ui.Button,
    ) -> None:
        """Page counter display."""
        return

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Navigate to the next page."""
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
