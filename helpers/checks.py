"""Command checks and permission predicates."""

import enum

import discord
from discord.ext.commands import Context, check

from helpers.config import get_config
from helpers.exceptions import (
    HierarchyError,
    MissingRoleOrPermission,
    ModuleDisabled,
    UserNotGuildOwner,
    UserNotOwner,
)


class PrivilegeLevel(enum.IntEnum):
    """Hierarchical privilege tiers for bot permission evaluation."""

    NONE = 0
    MOD = 1
    ADMIN = 2
    GUILD_OWNER = 3
    BOT_OWNER = 4

    @classmethod
    async def from_ctx(cls, ctx: Context) -> "PrivilegeLevel":
        """Resolve the effective PrivilegeLevel of the command invoker."""
        bot_config = getattr(ctx.bot, "config", None) or get_config()
        if bot_config.is_owner(ctx.author.id):
            return cls.BOT_OWNER

        if not ctx.guild:
            return cls.NONE

        if ctx.author.id == ctx.guild.owner_id:
            return cls.GUILD_OWNER

        if ctx.author.guild_permissions.administrator:
            return cls.ADMIN

        if await ctx.bot.guild_repo.has_role_type(ctx.author, "admin"):
            return cls.ADMIN

        if ctx.author.guild_permissions.manage_guild:
            return cls.MOD

        if await ctx.bot.guild_repo.has_role_type(ctx.author, "mod"):
            return cls.MOD

        return cls.NONE


def get_audit_reason(
    author: discord.User | discord.Member,
    reason: str,
    max_length: int = 512,
) -> str:
    """Format an audit log reason with moderator identity and reason."""
    formatted = f"Action by {author} ({author.id}): {reason}"
    return formatted[:max_length]


def is_owner():
    """Check if the user is a registered bot owner."""

    async def predicate(ctx: Context) -> bool:
        level = await PrivilegeLevel.from_ctx(ctx)
        if level < PrivilegeLevel.BOT_OWNER:
            raise UserNotOwner()
        return True

    return check(predicate)


def guildowner():
    """Check if the command invoker is the server owner or bot owner."""

    async def predicate(ctx: Context) -> bool:
        level = await PrivilegeLevel.from_ctx(ctx)
        if level < PrivilegeLevel.GUILD_OWNER:
            raise UserNotGuildOwner()
        return True

    return check(predicate)


def admin_or_permissions(**perms: bool):
    """Check if user has an admin role, administrator permission, or specific permissions."""

    async def predicate(ctx: Context) -> bool:
        if not ctx.guild:
            return True

        level = await PrivilegeLevel.from_ctx(ctx)
        if level >= PrivilegeLevel.ADMIN:
            return True

        if perms:
            author_perms = dict(ctx.author.guild_permissions)
            has_all = all(author_perms.get(p, False) for p, req in perms.items() if req)
            if has_all:
                return True

        raise MissingRoleOrPermission("admin", [p for p, req in perms.items() if req])

    return check(predicate)


def mod_or_permissions(**perms: bool):
    """Check if user has a mod role, admin role, manage_guild, or specific permissions."""

    async def predicate(ctx: Context) -> bool:
        if not ctx.guild:
            return True

        level = await PrivilegeLevel.from_ctx(ctx)
        if level >= PrivilegeLevel.MOD:
            return True

        if perms:
            author_perms = dict(ctx.author.guild_permissions)
            has_all = all(author_perms.get(p, False) for p, req in perms.items() if req)
            if has_all:
                return True

        raise MissingRoleOrPermission("mod", [p for p, req in perms.items() if req])

    return check(predicate)


def check_hierarchy(ctx: Context, target: discord.Member) -> None:
    """Verify that both the invoking moderator and the bot outrank the target member."""
    if not ctx.guild:
        return

    if target.id == ctx.guild.owner_id:
        raise HierarchyError("You cannot perform moderation actions against the server owner.")
    if target.id == ctx.bot.user.id:
        raise HierarchyError("I cannot perform moderation actions against myself.")
    if target.id == ctx.author.id:
        raise HierarchyError("You cannot perform moderation actions against yourself.")

    bot_config = getattr(ctx.bot, "config", None) or get_config()
    is_owner_invoker = bot_config.is_owner(ctx.author.id)
    is_guild_owner = ctx.author.id == ctx.guild.owner_id

    if not (is_owner_invoker or is_guild_owner) and ctx.author.top_role <= target.top_role:
        raise HierarchyError(
            f"Your highest role ({ctx.author.top_role.mention}) must be strictly higher than "
            f"{target.mention}'s highest role ({target.top_role.mention})."
        )

    bot_member = ctx.guild.me
    if bot_member.top_role <= target.top_role:
        raise HierarchyError(
            f"My highest role ({bot_member.top_role.mention}) must be strictly higher than "
            f"{target.mention}'s highest role ({target.top_role.mention}) to take action."
        )


def module_enabled(module_name: str):
    """Check if a specific module is enabled in the current guild."""

    async def predicate(ctx: Context) -> bool:
        if not ctx.guild:
            return True
        if ctx.bot.config.is_owner(ctx.author.id) or ctx.author.guild_permissions.administrator:
            return True
        is_enabled = await ctx.bot.guild_repo.is_module_enabled(ctx.guild.id, module_name)
        if not is_enabled:
            raise ModuleDisabled(module_name)
        return True

    return check(predicate)
