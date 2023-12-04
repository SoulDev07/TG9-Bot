"""Contains custom exceptions"""
from discord.ext import commands

class UserNotOwner(commands.CommandError):
    """Exception raised when a user is not the owner of the bot."""

    def __init__(self, custom_message="You cannot run this Command!"):
        self.message = custom_message
        super().__init__(self.message)
