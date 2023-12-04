"""Contains command checks"""

from helpers import json_manager
from discord.ext.commands import Context, check
from helpers.exceptions import UserNotOwner


def is_owner():
    """Checks if User is Owner"""

    async def predicate(ctx: Context):
        config = json_manager.load_config()
        if ctx.author.id not in config["owners"]:
            raise UserNotOwner
        return True

    return check(predicate)
