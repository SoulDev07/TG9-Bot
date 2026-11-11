"""Interactive category-based help menu views."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from helpers.embeds import EmbedColor, make_embed

if TYPE_CHECKING:
    from bot import DiscordBot

CATEGORIES: dict[str, dict[str, str]] = {
    "moderation": {
        "title": "🛡️ Moderation & Enforcement",
        "description": (
            "**Infraction Management:**\n"
            "• `/warn <member> [points] [reason]`: Issue points-weighted warning\n"
            "• `/warnings user <member>`: Paginated infraction history and active points\n"
            "• `/warnings delete <id>`: Pardon or delete a warning record\n"
            "• `/warnset decay <days>`: Configure points decay interval\n"
            "• `/warnset action list|set|delete`: Automated escalation thresholds\n"
            "• `/warnset reason list|set|delete`: Presets and point weights\n\n"
            "**Enforcement Toolkit:**\n"
            "• `/timeout <member> <duration> [reason]`: Temporary server timeout\n"
            "• `/kick <member> [reason]`: Kick member with audit log\n"
            "• `/ban <member> [reason]`: Permanent guild ban\n"
            "• `/tempban <member> <duration> [reason]`: Scheduled temporary ban\n"
            "• `/softban <member> [reason]`: Ban and immediately unban to clear chat\n"
            "• `/hackban <user_id> [reason]`: Pre-ban a user before they join\n"
            "• `/unban <user_id> [--reinvite]`: Revoke ban with optional DM invite\n"
            "• `/massban <user_ids...>`: Bulk ban multiple IDs with confirmation\n"
            "• `/purge <amount>`: Bulk delete recent channel messages\n\n"
            "**Case Auditing:**\n"
            "• `/case view <id>`: Inspect historical case and moderator\n"
            "• `/case edit <id> <reason>`: Live-edit database and Discord audit log embed\n"
            "• `/cases user <member>`: Search member moderation infraction history"
        ),
    },
    "general": {
        "title": "🛠️ General Utilities",
        "description": (
            "• `/info`: System metrics, gateway latency, and server stats\n"
            "• `/ping`: Gateway latency and API roundtrip latency\n"
            "• `/prefix [new_prefix]`: View or configure custom server prefix\n"
            "• `/server`: Direct invite link to support server\n"
            "• `/poll <question>`: Create an interactive button-based voting poll"
        ),
    },
    "fun": {
        "title": "🎮 Fun & Games",
        "description": (
            "• `/coinflip`: Flip a two-sided coin\n"
            "• `/rps`: Play interactive Rock, Paper, Scissors with buttons"
        ),
    },
    "setup": {
        "title": "⚙️ Server Setup & Configuration",
        "description": (
            "• `/setup`: Interactive onboarding wizard with channel and role pickers\n"
            "• `/settings`: Dynamic dashboard with live module toggle buttons\n"
            "• `/roles add|remove|list`: Configure Admin and Moderator role tiers"
        ),
    },
    "owner": {
        "title": "👑 Bot Owner Controls",
        "description": (
            "• `sync [scope]`: Synchronize application slash command tree\n"
            "• `load|unload|reload <ext>`: Dynamic runtime extension lifecycle\n"
            "• `cogs`: List currently active cogs and command counts\n"
            "• `blacklist add|remove`: Global user access restriction\n"
            "• `status add|remove|set`: Rotating bot presence control\n"
            "• `shutdown`: Safe process termination"
        ),
    },
}


class HelpCategorySelect(discord.ui.Select["HelpMenuView"]):
    """Dropdown menu for switching between command help categories."""

    def __init__(self) -> None:
        options = [
            discord.SelectOption(
                label="Home Overview",
                value="home",
                description="General bot overview and quick links",
                emoji="🏠",
                default=True,
            ),
            discord.SelectOption(
                label="Moderation",
                value="moderation",
                description="Warnings, escalations, bans, timeouts, and cases",
                emoji="🛡️",
            ),
            discord.SelectOption(
                label="Setup & Configuration",
                value="setup",
                description="Interactive /setup wizard, /settings dashboard, and roles",
                emoji="⚙️",
            ),
            discord.SelectOption(
                label="General Utilities",
                value="general",
                description="Bot info, ping, prefix, and live voting polls",
                emoji="🛠️",
            ),
            discord.SelectOption(
                label="Fun & Games",
                value="fun",
                description="Coinflip and interactive Rock Paper Scissors",
                emoji="🎮",
            ),
            discord.SelectOption(
                label="Owner Commands",
                value="owner",
                description="Global tree sync, extension reloads, and blacklists",
                emoji="👑",
            ),
        ]
        super().__init__(
            placeholder="Select a category to view commands...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle category selection and update embed."""
        assert self.view is not None
        selected = self.values[0]

        for option in self.options:
            option.default = option.value == selected

        if selected == "home":
            embed = self.view.build_home_embed()
        else:
            cat = CATEGORIES[selected]
            embed = make_embed(
                title=cat["title"],
                description=cat["description"],
                color=EmbedColor.INFO,
                footer="Use the dropdown menu below to explore other categories.",
            )

        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpMenuView(discord.ui.View):
    """Interactive help menu with category selection dropdown."""

    def __init__(self, bot: DiscordBot, invoker_id: int, timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.invoker_id = invoker_id
        self.add_item(HelpCategorySelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Enforce that only the help command invoker can use the dropdown."""
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "You cannot interact with another user's help menu. Run `/help` yourself!",
                ephemeral=True,
            )
            return False
        return True

    def build_home_embed(self) -> discord.Embed:
        """Construct the default home overview embed."""
        bot_user = self.bot.user
        bot_name = bot_user.name if bot_user else "TG9"
        bot_avatar = bot_user.display_avatar.url if bot_user else None

        description = (
            f"Welcome to **{bot_name}**! A modern, general-purpose Discord bot built for "
            "effortless server management, reliable moderation, and interactive games.\n\n"
            "**Key Features:**\n"
            "• **Plug & Play Setup:** Run `/setup` for interactive channel and role selection\n"
            "• **Live Settings:** Run `/settings` to toggle modules on and off in real-time\n"
            "• **Tiered Warnings:** Point weights, automatic decay, and threshold escalations\n"
            "• **ModLog Cases:** Sequentially numbered cases with live audit embed editing\n\n"
            "*Select a category from the dropdown menu below to view full command syntax.*"
        )

        return make_embed(
            title=f"{bot_name} Command Directory",
            description=description,
            color=EmbedColor.INFO,
            author_name=bot_name,
            author_icon=bot_avatar,
            footer="TG9 Bot • Python 3.12+ • discord.py 2.x",
        )
