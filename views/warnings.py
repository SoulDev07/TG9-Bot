"""Interactive pagination view for member warning histories."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

import discord

from core.embeds import EmbedColor, make_embed
from views.pagination import BasePaginationView

if TYPE_CHECKING:
    from core.db.models import WarningRecord


class WarningHistoryPaginationView(BasePaginationView["WarningRecord"]):
    """Paginated view for inspecting a member's active and decayed warnings."""

    def __init__(
        self,
        warnings: list[WarningRecord],
        target_user: discord.User | discord.Member,
        active_points: int,
        invoker_id: int,
        page_size: int = 5,
    ) -> None:
        super().__init__(items=warnings, invoker_id=invoker_id, page_size=page_size)
        self.target_user = target_user
        self.active_points = active_points

    @property
    def warnings(self) -> list[WarningRecord]:
        """Convenience property for accessing warning records."""
        return self.items

    @override
    def build_embed(self) -> discord.Embed:
        """Construct the embed for the active page."""
        page_warnings = self.get_current_page_items()

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
