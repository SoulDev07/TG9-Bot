"""Contains command checks"""

from discord.ext.commands import Context, check

from helpers.config import get_config
from helpers.exceptions import UserNotOwner


def is_owner():
    """Checks if User is Owner"""

    async def predicate(ctx: Context) -> bool:
        config = get_config()
        if not config.is_owner(ctx.author.id):
            raise UserNotOwner
        return True

    return check(predicate)
