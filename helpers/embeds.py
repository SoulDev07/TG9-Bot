"""Standardized embed factory implementing the Builder/Factory pattern for UI embeds."""

from datetime import datetime
from typing import Any

import discord


class EmbedColor:
    """Design system color constants."""

    SUCCESS = 0x42F56C
    ERROR = 0xE02B2B
    WARNING = 0xF59E42
    INFO = 0x5865F2
    DEFAULT = 0x42F56C


class EmbedFactory:
    """Factory creating consistent, styled Discord embeds across the application."""

    @staticmethod
    def create(
        *,
        title: str | None = None,
        description: str | None = None,
        color: int = EmbedColor.DEFAULT,
        fields: list[tuple[str, str, bool]] | None = None,
        footer: str | None = None,
        footer_icon: str | None = None,
        timestamp: datetime | None = None,
        author_name: str | None = None,
        author_icon: str | None = None,
    ) -> discord.Embed:
        """Create a customized discord.Embed with optional metadata."""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=timestamp,
        )

        if fields:
            for name, value, inline in fields:
                embed.add_field(name=name, value=value, inline=inline)

        if footer:
            footer_kwargs: dict[str, Any] = {"text": footer}
            if footer_icon:
                footer_kwargs["icon_url"] = footer_icon
            embed.set_footer(**footer_kwargs)

        if author_name:
            author_kwargs: dict[str, Any] = {"name": author_name}
            if author_icon:
                author_kwargs["icon_url"] = author_icon
            embed.set_author(**author_kwargs)

        return embed

    @classmethod
    def success(
        cls,
        title: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> discord.Embed:
        """Create a green success embed."""
        return cls.create(title=title, description=description, color=EmbedColor.SUCCESS, **kwargs)

    @classmethod
    def error(
        cls,
        title: str = "Error!",
        description: str | None = None,
        **kwargs: Any,
    ) -> discord.Embed:
        """Create a red error embed."""
        return cls.create(title=title, description=description, color=EmbedColor.ERROR, **kwargs)

    @classmethod
    def warning(
        cls,
        title: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> discord.Embed:
        """Create an amber warning embed."""
        return cls.create(title=title, description=description, color=EmbedColor.WARNING, **kwargs)

    @classmethod
    def info(
        cls,
        title: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> discord.Embed:
        """Create a blue/purple informational embed."""
        return cls.create(title=title, description=description, color=EmbedColor.INFO, **kwargs)
