"""Command checks and permission predicates."""

from discord.ext.commands import Context, check

from helpers.config import get_config
from helpers.exceptions import ModuleDisabled, UserNotOwner


def is_owner():
    """Check if the user is a registered bot owner."""

    async def predicate(ctx: Context) -> bool:
        config = get_config()
        if not config.is_owner(ctx.author.id):
            raise UserNotOwner
        return True

    return check(predicate)


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
