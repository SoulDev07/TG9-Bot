"""Custom exceptions for bot commands and checks."""

from discord.ext import commands


class UserNotOwner(commands.CommandError):
    """Exception raised when a user is not the owner of the bot."""

    def __init__(self, custom_message: str = "You cannot run this Command!"):
        self.message = custom_message
        super().__init__(self.message)


class ModuleDisabled(commands.CheckFailure):
    """Exception raised when a command is executed in a disabled guild module."""

    def __init__(self, module_name: str):
        self.module_name = module_name
        super().__init__(f"The `{module_name}` module is disabled on this server.")
