"""Custom exceptions for bot commands and checks."""

from discord.ext import commands


class UserNotOwner(commands.CommandError):
    """Exception raised when a user is not the owner of the bot."""

    def __init__(self, custom_message: str = "You cannot run this Command!"):
        self.message = custom_message
        super().__init__(self.message)


class UserNotGuildOwner(commands.CheckFailure):
    """Exception raised when a command requires guild ownership."""

    def __init__(self, message: str = "You must be the server owner to execute this command!"):
        super().__init__(message)


class MissingRoleOrPermission(commands.CheckFailure):
    """Exception raised when a user lacks required guild roles and permissions."""

    def __init__(self, role_type: str, missing_permissions: list[str]):
        self.role_type = role_type
        self.missing_permissions = missing_permissions
        perms_str = ", ".join(f"`{p}`" for p in missing_permissions) if missing_permissions else ""
        super().__init__(
            f"You require a designated **{role_type.capitalize()}** role"
            + (f" or permission: {perms_str}" if perms_str else "")
            + " to run this command."
        )


class HierarchyError(commands.CheckFailure):
    """Exception raised when a role hierarchy conflict prevents moderation."""

    def __init__(self, message: str):
        super().__init__(message)


class ModuleDisabled(commands.CheckFailure):
    """Exception raised when a command is executed in a disabled guild module."""

    def __init__(self, module_name: str):
        self.module_name = module_name
        super().__init__(f"The `{module_name}` module is disabled on this server.")
