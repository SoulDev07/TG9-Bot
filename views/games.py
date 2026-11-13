"""Interactive game views and components."""

from __future__ import annotations

import random

import discord

from core.embeds import EmbedColor, make_embed

CHOICES: dict[str, int] = {
    "rock": 0,
    "paper": 1,
    "scissors": 2,
}

EMOJIS: dict[str, str] = {
    "rock": "🪨",
    "paper": "📰",
    "scissors": "✂️",
}


class RockPaperScissorsView(discord.ui.View):
    """Interactive button-based Rock, Paper, Scissors game."""

    def __init__(self, invoker: discord.User | discord.Member, timeout: float = 60.0) -> None:
        super().__init__(timeout=timeout)
        self.invoker = invoker
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Enforce that only the game challenger can press buttons."""
        if interaction.user.id != self.invoker.id:
            await interaction.response.send_message(
                "You cannot play in someone else's game. Start your own with `/rps`!",
                ephemeral=True,
            )
            return False
        return True

    async def _handle_choice(self, interaction: discord.Interaction, user_choice: str) -> None:
        """Evaluate round result against bot pick and render results."""
        bot_choice = random.choice(list(CHOICES.keys()))
        user_idx = CHOICES[user_choice]
        bot_idx = CHOICES[bot_choice]

        user_emoji = EMOJIS[user_choice]
        bot_emoji = EMOJIS[bot_choice]

        if user_idx == bot_idx:
            result_title = "It's a Draw!"
            result_color = EmbedColor.WARNING
            result_desc = (
                f"We both picked **{user_choice.title()}** {user_emoji}!\n"
                "A tense standoff, nobody wins this round."
            )
        elif (user_idx - bot_idx) % 3 == 1:
            result_title = "You Won!"
            result_color = EmbedColor.SUCCESS
            result_desc = (
                f"**Your Choice:** {user_choice.title()} {user_emoji}\n"
                f"**My Choice:** {bot_choice.title()} {bot_emoji}\n\n"
                f"Nicely played, **{user_choice.title()}** beats **{bot_choice.title()}**!"
            )
        else:
            result_title = "You Lost!"
            result_color = EmbedColor.ERROR
            result_desc = (
                f"**Your Choice:** {user_choice.title()} {user_emoji}\n"
                f"**My Choice:** {bot_choice.title()} {bot_emoji}\n\n"
                f"Better luck next time, **{bot_choice.title()}** beats **{user_choice.title()}**!"
            )

        embed = make_embed(
            title=result_title,
            description=result_desc,
            color=result_color,
            author_name=self.invoker.display_name,
            author_icon=self.invoker.display_avatar.url,
        )

        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Rock", emoji="🪨", style=discord.ButtonStyle.primary)
    async def rock_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Choose Rock."""
        await self._handle_choice(interaction, "rock")

    @discord.ui.button(label="Paper", emoji="📰", style=discord.ButtonStyle.primary)
    async def paper_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Choose Paper."""
        await self._handle_choice(interaction, "paper")

    @discord.ui.button(label="Scissors", emoji="✂️", style=discord.ButtonStyle.primary)
    async def scissors_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Choose Scissors."""
        await self._handle_choice(interaction, "scissors")

    async def on_timeout(self) -> None:
        """Disable buttons upon game timeout."""
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self.message:
            timeout_embed = make_embed(
                title="Game Timed Out",
                description="No move was made in time. The game has ended.",
                color=EmbedColor.INFO,
            )
            try:
                await self.message.edit(embed=timeout_embed, view=self)
            except discord.HTTPException:
                pass
