"""Interactive self-assignable roles view and persistent menu button."""

from __future__ import annotations

import discord

from core.embeds import error_embed, info_embed, make_embed, success_embed
from core.logger import get_logger

logger = get_logger()


class SelfRoleSelect(discord.ui.Select):
    """Dropdown menu populated with self-assignable roles."""

    def __init__(
        self,
        roles: list[discord.Role],
        member: discord.Member,
        row: int = 0,
        placeholder: str = "Select roles to assign or remove...",
    ) -> None:
        self.roles_map = {r.id: r for r in roles}
        options: list[discord.SelectOption] = []

        for role in roles[:25]:
            has_role = role in member.roles
            options.append(
                discord.SelectOption(
                    label=role.name[:100],
                    value=str(role.id),
                    description="Assigned (uncheck to remove)" if has_role else "Click to assign",
                    default=has_role,
                )
            )

        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=min(len(options), 25),
            options=options,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle member role toggle selection."""
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return

        member = interaction.user
        selected_ids = {int(v) for v in self.values}

        to_add: list[discord.Role] = []
        to_remove: list[discord.Role] = []

        for role_id, role in self.roles_map.items():
            if role_id in selected_ids and role not in member.roles:
                to_add.append(role)
            elif role_id not in selected_ids and role in member.roles:
                to_remove.append(role)

        if not to_add and not to_remove:
            embed = info_embed(
                title="No Changes",
                description="Your role selections are identical to your current roles.",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            if to_add:
                await member.add_roles(*to_add, reason="Self-assigned roles via TG9")
            if to_remove:
                await member.remove_roles(*to_remove, reason="Self-removed roles via TG9")
        except discord.Forbidden:
            embed = error_embed(
                title="Permission Error",
                description="I cannot update some of these roles. Ensure my role is placed higher than them.",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        fields: list[tuple[str, str, bool]] = []
        if to_add:
            fields.append(("Added Roles", ", ".join(r.mention for r in to_add), False))
        if to_remove:
            fields.append(("Removed Roles", ", ".join(r.mention for r in to_remove), False))

        embed = success_embed(
            title="Roles Updated",
            description="Your self-assigned roles have been successfully updated.",
            fields=fields,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class SelfRoleSelectView(discord.ui.View):
    """Ephemeral view displaying the dropdown role picker."""

    def __init__(self, roles: list[discord.Role], member: discord.Member, timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.invoker_id = member.id
        # Support up to 125 self-roles across 5 action rows (25 roles per row)
        for index, chunk_start in enumerate(range(0, min(len(roles), 125), 25)):
            chunk = roles[chunk_start : chunk_start + 25]
            placeholder = (
                "Select roles to assign or remove..."
                if len(roles) <= 25
                else f"Select roles ({chunk_start + 1}-{chunk_start + len(chunk)})..."
            )
            self.add_item(SelfRoleSelect(chunk, member, row=index, placeholder=placeholder))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "You cannot use another member's role menu.",
                ephemeral=True,
            )
            return False
        return True


class PersistentSelfRoleView(discord.ui.View):
    """Persistent button view stationed in channels to launch ephemeral role pickers."""

    def __init__(self, bot=None) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Pick Roles",
        style=discord.ButtonStyle.primary,
        emoji="🎭",
        custom_id="tg9:selfroles:open_picker",
    )
    async def open_picker_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Dynamically fetch self-roles for this guild and open an ephemeral picker."""
        guild = interaction.guild
        if not guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return

        bot = interaction.client
        role_ids = await bot.guild_repo.get_roles(guild.id, "selfrole")

        if not role_ids:
            embed = error_embed(
                title="No Self-Roles Configured",
                description="There are currently no self-assignable roles configured on this server.",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        available_roles: list[discord.Role] = []
        for rid in sorted(role_ids):
            role = guild.get_role(rid)
            if role is not None and role < guild.me.top_role and not role.managed:
                available_roles.append(role)

        if not available_roles:
            embed = error_embed(
                title="No Assignable Roles",
                description=(
                    "Configured self-roles either no longer exist or are higher than my highest role."
                ),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = make_embed(
            title="🎭 Self-Assignable Roles",
            description=(
                "Use the menu below to assign or remove roles:\n"
                "• Roles with checkmarks are currently assigned to you.\n"
                "• Check or uncheck roles and submit to update."
            ),
        )
        view = SelfRoleSelectView(roles=available_roles, member=interaction.user)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
