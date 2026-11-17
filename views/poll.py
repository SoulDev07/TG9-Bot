"""Interactive poll views with live voting and counter tallying."""

from __future__ import annotations

import discord

from core.embeds import EmbedColor, make_embed


def _render_bar(pct: float, length: int = 10) -> str:
    """Render a visual progress bar for vote percentages."""
    filled = round(pct * length)
    return "█" * filled + "░" * (length - filled)


class PollView(discord.ui.View):
    """Interactive button-based voting poll with live vote distribution updates."""

    def __init__(
        self,
        question: str,
        creator: discord.User | discord.Member,
        timeout: float = 86400.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.question = question
        self.creator = creator
        self.votes: dict[int, str] = {}
        self.message: discord.Message | None = None

    def build_embed(self, closed: bool = False) -> discord.Embed:
        """Construct poll embed with live vote tallies and percentage bars."""
        total = len(self.votes)
        yes_count = sum(1 for v in self.votes.values() if v == "yes")
        no_count = sum(1 for v in self.votes.values() if v == "no")
        abstain_count = sum(1 for v in self.votes.values() if v == "abstain")

        yes_pct = (yes_count / total) if total else 0.0
        no_pct = (no_count / total) if total else 0.0
        abstain_pct = (abstain_count / total) if total else 0.0

        status_prefix = "📊 **[Closed] Poll:**" if closed else "📊 **Poll:**"
        content = (
            f"### {self.question}\n\n"
            f"**Yes** ({yes_count} votes • {yes_pct:.0%})\n"
            f"`{_render_bar(yes_pct)}`\n\n"
            f"**No** ({no_count} votes • {no_pct:.0%})\n"
            f"`{_render_bar(no_pct)}`\n\n"
            f"**Abstain** ({abstain_count} votes • {abstain_pct:.0%})\n"
            f"`{_render_bar(abstain_pct)}`\n\n"
            f"*Total Votes Cast:* `{total}`"
        )

        return make_embed(
            title=f"{status_prefix} {self.question}",
            description=content,
            color=EmbedColor.INFO if not closed else EmbedColor.SUCCESS,
            author_name=f"Poll by {self.creator.display_name}",
            author_icon=self.creator.display_avatar.url,
            footer="Click a button below to cast or change your vote!"
            if not closed
            else "Voting has concluded.",
        )

    def _update_button_labels(self) -> None:
        """Update button labels with current vote counts."""
        yes_count = sum(1 for v in self.votes.values() if v == "yes")
        no_count = sum(1 for v in self.votes.values() if v == "no")
        abstain_count = sum(1 for v in self.votes.values() if v == "abstain")

        self.yes_button.label = f"Yes ({yes_count})"
        self.no_button.label = f"No ({no_count})"
        self.abstain_button.label = f"Abstain ({abstain_count})"

    async def _handle_vote(self, interaction: discord.Interaction, choice: str) -> None:
        """Record or update user vote and edit message."""
        prev_vote = self.votes.get(interaction.user.id)
        if prev_vote == choice:
            del self.votes[interaction.user.id]
            msg = f"Your vote for **{choice.title()}** has been removed."
        else:
            self.votes[interaction.user.id] = choice
            msg = f"Your vote has been cast for **{choice.title()}**!"

        self._update_button_labels()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        await interaction.followup.send(msg, ephemeral=True)

    @discord.ui.button(label="Yes (0)", emoji="👍", style=discord.ButtonStyle.success)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Cast Yes vote."""
        await self._handle_vote(interaction, "yes")

    @discord.ui.button(label="No (0)", emoji="👎", style=discord.ButtonStyle.danger)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Cast No vote."""
        await self._handle_vote(interaction, "no")

    @discord.ui.button(label="Abstain (0)", emoji="🤷", style=discord.ButtonStyle.secondary)
    async def abstain_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Cast Abstain vote."""
        await self._handle_vote(interaction, "abstain")

    @discord.ui.button(label="End Poll", style=discord.ButtonStyle.secondary, row=1)
    async def end_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """End poll prematurely (creator or administrator only)."""
        is_creator = interaction.user.id == self.creator.id
        is_admin = (
            interaction.guild
            and isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.administrator
        )

        if not (is_creator or is_admin):
            await interaction.response.send_message(
                "Only the poll creator or a server administrator can close this poll.",
                ephemeral=True,
            )
            return

        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        await interaction.response.edit_message(embed=self.build_embed(closed=True), view=self)
        self.stop()
