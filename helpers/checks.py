"""Contains command checks"""

from discord.ext.commands import Context, check

from helpers import json_manager
from helpers.exceptions import UserNotOwner


def is_owner():
    """Checks if User is Owner"""

    async def predicate(ctx: Context) -> bool:
        config = json_manager.load_config()
        if ctx.author.id not in config["owners"]:
            raise UserNotOwner
        return True

    return check(predicate)
