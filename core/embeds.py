"""Pythonic embed generation functions and design tokens."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import discord

if TYPE_CHECKING:
    from core.db.models import ModCase


class EmbedColor:
    """Design system color constants."""

    SUCCESS: int = 0x42F56C
    ERROR: int = 0xE02B2B
    WARNING: int = 0xF59E42
    INFO: int = 0x5865F2
    DEFAULT: int = 0x42F56C


def make_embed(
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


def success_embed(
    title: str | None = None,
    description: str | None = None,
    **kwargs: Any,
) -> discord.Embed:
    """Create a green success embed."""
    return make_embed(title=title, description=description, color=EmbedColor.SUCCESS, **kwargs)


def error_embed(
    title: str = "Error!",
    description: str | None = None,
    **kwargs: Any,
) -> discord.Embed:
    """Create a red error embed."""
    return make_embed(title=title, description=description, color=EmbedColor.ERROR, **kwargs)


def warning_embed(
    title: str | None = None,
    description: str | None = None,
    **kwargs: Any,
) -> discord.Embed:
    """Create an amber warning embed."""
    return make_embed(title=title, description=description, color=EmbedColor.WARNING, **kwargs)


def info_embed(
    title: str | None = None,
    description: str | None = None,
    **kwargs: Any,
) -> discord.Embed:
    """Create a blue/purple informational embed."""
    return make_embed(title=title, description=description, color=EmbedColor.INFO, **kwargs)


def modlog_case_embed(
    case: ModCase,
    user: discord.User | discord.Member | None = None,
    moderator: discord.User | discord.Member | None = None,
) -> discord.Embed:
    """Construct a standardized embed representing a recorded moderation case."""
    action_colors = {
        "warn": EmbedColor.WARNING,
        "kick": 0xFFA500,
        "ban": EmbedColor.ERROR,
        "unban": EmbedColor.SUCCESS,
        "timeout": EmbedColor.WARNING,
    }
    color = action_colors.get(case.action.lower(), EmbedColor.INFO)
    user_display = f"{user} ({user.id})" if user else f"User ID: {case.user_id}"
    mod_display = (
        f"{moderator} ({moderator.id})" if moderator else f"Moderator ID: {case.moderator_id}"
    )

    return make_embed(
        title=f"Case #{case.case_number} | {case.action.upper()}",
        color=color,
        fields=[
            ("Target", user_display, True),
            ("Moderator", mod_display, True),
            ("Reason", case.reason, False),
        ],
        timestamp=case.created_at,
        footer=f"Case ID: {case.id or case.case_number}",
    )
