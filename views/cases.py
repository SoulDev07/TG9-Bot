"""Interactive pagination view for moderation case histories."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

import discord

from core.embeds import EmbedColor, make_embed
from views.pagination import BasePaginationView

if TYPE_CHECKING:
    from core.db.models import ModCase


class CaseHistoryPaginationView(BasePaginationView["ModCase"]):
    """Paginated view for browsing a member's moderation infractions history."""

    def __init__(
        self,
        cases: list[ModCase],
        target_user: discord.User | discord.Member,
        invoker_id: int,
        page_size: int = 5,
    ) -> None:
        super().__init__(items=cases, invoker_id=invoker_id, page_size=page_size)
        self.target_user = target_user

    @property
    def cases(self) -> list[ModCase]:
        """Convenience property for accessing the case records."""
        return self.items

    @override
    def build_embed(self) -> discord.Embed:
        """Construct the embed for the active page."""
        page_cases = self.get_current_page_items()

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
