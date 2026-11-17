"""Interactive Discord modal-based embed builder and live message editor views."""

from __future__ import annotations

import contextlib
import discord

from core.embeds import error_embed, success_embed


def parse_color(color_str: str | None) -> int:
    """Parse color string from hex or color names into an integer RGB value."""
    if not color_str:
        return 0x5865F2
    clean = color_str.strip().lower()
    named_colors = {
        "red": 0xE02B2B,
        "green": 0x42F56C,
        "blue": 0x5865F2,
        "yellow": 0xFEE75C,
        "orange": 0xF59E42,
        "purple": 0x9B59B6,
        "dark": 0x2B2D31,
        "white": 0xFFFFFF,
        "blurple": 0x5865F2,
    }
    if clean in named_colors:
        return named_colors[clean]
    clean_hex = clean.lstrip("#").removeprefix("0x")
    try:
        return int(clean_hex, 16)
    except ValueError:
        return 0x5865F2


class EmbedContentModal(discord.ui.Modal, title="Embed Core Content"):
    """Modal for editing embed title, description, and accent color."""

    def __init__(self, current_embed: discord.Embed, builder_view: EmbedBuilderView) -> None:
        super().__init__()
        self.builder_view = builder_view

        self.embed_title = discord.ui.TextInput(
            label="Title",
            placeholder="Embed header title",
            default=current_embed.title or "",
            max_length=256,
            required=False,
        )
        self.embed_desc = discord.ui.TextInput(
            label="Description",
            placeholder="Main body text (supports markdown)",
            default=current_embed.description or "",
            style=discord.TextStyle.paragraph,
            max_length=4000,
            required=False,
        )
        hex_color = f"#{current_embed.color.value:06x}" if current_embed.color else "#5865F2"
        self.embed_color = discord.ui.TextInput(
            label="Accent Color",
            placeholder="#5865F2, red, green, blue, purple, dark",
            default=hex_color,
            max_length=20,
            required=False,
        )

        self.add_item(self.embed_title)
        self.add_item(self.embed_desc)
        self.add_item(self.embed_color)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Apply core content changes and refresh live preview."""
        self.builder_view.current_embed.title = self.embed_title.value.strip() or None
        self.builder_view.current_embed.description = self.embed_desc.value.strip() or None
        color_val = parse_color(self.embed_color.value)
        self.builder_view.current_embed.color = discord.Color(color_val)

        await self.builder_view.refresh_preview(interaction)


class EmbedFieldModal(discord.ui.Modal, title="Add Embed Field"):
    """Modal for appending a field to the embed."""

    def __init__(self, builder_view: EmbedBuilderView) -> None:
        super().__init__()
        self.builder_view = builder_view

        self.field_name = discord.ui.TextInput(
            label="Field Name",
            placeholder="Field header title",
            max_length=256,
            required=True,
        )
        self.field_value = discord.ui.TextInput(
            label="Field Value",
            placeholder="Field body content",
            style=discord.TextStyle.paragraph,
            max_length=1024,
            required=True,
        )
        self.inline_opt = discord.ui.TextInput(
            label="Inline Display (yes/no)",
            placeholder="Type 'yes' or 'no'",
            default="no",
            max_length=5,
            required=False,
        )

        self.add_item(self.field_name)
        self.add_item(self.field_value)
        self.add_item(self.inline_opt)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Append field and update live preview."""
        is_inline = self.inline_opt.value.strip().lower() in ("yes", "y", "true", "1")
        self.builder_view.current_embed.add_field(
            name=self.field_name.value.strip(),
            value=self.field_value.value.strip(),
            inline=is_inline,
        )
        await self.builder_view.refresh_preview(interaction)


class EmbedMediaModal(discord.ui.Modal, title="Images & Footer"):
    """Modal for configuring thumbnail, image, and footer."""

    def __init__(self, current_embed: discord.Embed, builder_view: EmbedBuilderView) -> None:
        super().__init__()
        self.builder_view = builder_view

        self.thumb_url = discord.ui.TextInput(
            label="Thumbnail URL",
            placeholder="https://example.com/thumb.png",
            default=current_embed.thumbnail.url if current_embed.thumbnail else "",
            max_length=500,
            required=False,
        )
        self.image_url = discord.ui.TextInput(
            label="Large Banner Image URL",
            placeholder="https://example.com/banner.png",
            default=current_embed.image.url if current_embed.image else "",
            max_length=500,
            required=False,
        )
        self.footer_text = discord.ui.TextInput(
            label="Footer Text",
            placeholder="Footer note",
            default=current_embed.footer.text if current_embed.footer else "",
            max_length=256,
            required=False,
        )

        self.add_item(self.thumb_url)
        self.add_item(self.image_url)
        self.add_item(self.footer_text)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Apply image and footer changes and update live preview."""
        t_url = self.thumb_url.value.strip() or None
        i_url = self.image_url.value.strip() or None
        f_text = self.footer_text.value.strip() or None

        self.builder_view.current_embed.set_thumbnail(url=t_url)
        self.builder_view.current_embed.set_image(url=i_url)
        if f_text:
            self.builder_view.current_embed.set_footer(text=f_text)
        else:
            self.builder_view.current_embed.remove_footer()

        await self.builder_view.refresh_preview(interaction)


class EmbedBuilderView(discord.ui.View):
    """Interactive embed builder view with live preview controls and channel dispatch."""

    def __init__(
        self,
        invoker_id: int,
        existing_embed: discord.Embed | None = None,
        target_message: discord.Message | None = None,
    ) -> None:
        super().__init__(timeout=600.0)
        self.invoker_id = invoker_id
        self.target_message = target_message
        self.message: discord.Message | None = None

        if existing_embed:
            self.current_embed = existing_embed.copy()
        else:
            self.current_embed = discord.Embed(
                title="Embed Title",
                description="Click **Content** to edit this description.",
                color=discord.Color(0x5865F2),
            )

        if self.target_message:
            self.send_here_button.label = "Save Changes"
            self.send_here_button.style = discord.ButtonStyle.success

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verify only the invoker interacts with the builder."""
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "You cannot interact with another user's embed builder.",
                ephemeral=True,
            )
            return False
        return True

    async def refresh_preview(self, interaction: discord.Interaction) -> None:
        """Edit the builder message to reflect current embed modifications."""
        await interaction.response.edit_message(
            content="### 🛠️ Interactive Embed Builder (Live Preview)",
            embed=self.current_embed,
            view=self,
        )

    @discord.ui.button(label="Content", style=discord.ButtonStyle.primary, emoji="📝", row=0)
    async def edit_content(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Open the modal to edit title, description, and color."""
        modal = EmbedContentModal(self.current_embed, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Add Field", style=discord.ButtonStyle.primary, emoji="➕", row=0)
    async def add_field(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Open the modal to append a new field."""
        if len(self.current_embed.fields) >= 25:
            await interaction.response.send_message(
                "Embeds cannot exceed 25 fields.", ephemeral=True
            )
            return
        modal = EmbedFieldModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Images & Footer", style=discord.ButtonStyle.primary, emoji="🖼️", row=0)
    async def edit_media(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Open the modal to edit thumbnail, banner image, and footer."""
        modal = EmbedMediaModal(self.current_embed, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Clear Fields", style=discord.ButtonStyle.secondary, emoji="🗑️", row=0)
    async def clear_fields(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Clear all custom fields on the embed."""
        self.current_embed.clear_fields()
        await self.refresh_preview(interaction)

    @discord.ui.button(label="Send Here", style=discord.ButtonStyle.success, emoji="📤", row=1)
    async def send_here_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        """Dispatch embed to the current channel or save edits to the target message."""
        if self.target_message:
            try:
                await self.target_message.edit(embed=self.current_embed)
                await interaction.response.send_message(
                    embed=success_embed(
                        title="Embed Updated",
                        description=f"Successfully updated message [`{self.target_message.id}`]({self.target_message.jump_url}) with new embed.",
                    ),
                    ephemeral=True,
                )
                self.stop()
            except discord.Forbidden:
                await interaction.response.send_message(
                    embed=error_embed(description="Cannot edit message: missing permissions."),
                    ephemeral=True,
                )
            except discord.HTTPException as err:
                await interaction.response.send_message(
                    embed=error_embed(description=f"Failed to edit message: `{err}`"),
                    ephemeral=True,
                )
            return

        if not interaction.channel:
            await interaction.response.send_message(
                "Cannot determine channel destination.", ephemeral=True
            )
            return

        try:
            await interaction.channel.send(embed=self.current_embed)
            await interaction.response.send_message(
                embed=success_embed(
                    description=f"Embed published to {interaction.channel.mention}."
                ),
                ephemeral=True,
            )
            self.stop()
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed(description="I lack permissions to send embeds in this channel."),
                ephemeral=True,
            )

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text, discord.ChannelType.news],
        placeholder="Or choose a target channel to send...",
        row=2,
    )
    async def select_channel(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ) -> None:
        """Send the embed to the selected guild channel."""
        selected_channel = select.values[0]
        channel = interaction.guild.get_channel(selected_channel.id) if interaction.guild else None
        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Invalid channel selected.", ephemeral=True)
            return

        try:
            await channel.send(embed=self.current_embed)
            await interaction.response.send_message(
                embed=success_embed(
                    description=f"Embed successfully dispatched to {channel.mention}."
                ),
                ephemeral=True,
            )
            self.stop()
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed(
                    description=f"I do not have permission to send embeds in {channel.mention}."
                ),
                ephemeral=True,
            )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="✖️", row=1)
    async def cancel_builder(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Abort embed building session."""
        self.stop()
        await interaction.response.send_message("Embed builder session closed.", ephemeral=True)
        if self.message:
            with contextlib.suppress(discord.HTTPException):
                await self.message.delete()
