"""Stores moderation commands of Bot"""

import discord
from discord.ext import commands
from discord.ext.commands import Context

from helpers import checks, exceptions
from helpers.embeds import EmbedFactory
from services.moderation import ModerationService


class Moderation(commands.Cog, name="moderation"):
    """Moderation Commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: Context) -> bool:
        """Verify the moderation module is enabled for the invoking guild."""
        if not ctx.guild:
            return True
        if ctx.bot.config.is_owner(ctx.author.id) or ctx.author.guild_permissions.administrator:
            return True
        is_enabled = await ctx.bot.guild_repo.is_module_enabled(ctx.guild.id, "moderation")
        if not is_enabled:
            raise exceptions.ModuleDisabled("moderation")
        return True

    @commands.hybrid_command(
        name="say",
        aliases=["echo"],
        description="The bot will say anything you want",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def say(self, ctx: Context, *, sentence: str):
        """The bot will say anything you want."""
        await ctx.send(sentence)

    @commands.hybrid_command(
        name="embed",
        description="The bot will say anything you want in embeds",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def embed(self, ctx: Context, *, sentence: str):
        """The bot will say anything you want in embeds."""
        embed = EmbedFactory.success(description=sentence)
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="warn",
        description="Warns a user in their private messages",
    )
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def warn(
        self,
        ctx: Context,
        member: discord.Member,
        *,
        reason: str = "Not specified",
    ):
        """Warns a user in their private messages."""
        await ModerationService.warn_member(ctx, member, reason)
        embed = EmbedFactory.success(
            title="User Warned!",
            description=f"**{member}** was warned by **{ctx.author}**!",
            fields=[("Reason", reason, False)],
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="kick", description="Kick a user out of the server")
    @commands.guild_only()
    @checks.mod_or_permissions(kick_members=True)
    async def kick(
        self,
        ctx: Context,
        member: discord.Member,
        *,
        reason: str = "Not specified",
    ):
        """Kick a user out of the server."""
        try:
            await ModerationService.kick_member(ctx, member, reason)
            embed = EmbedFactory.success(
                title="User Kicked!",
                description=f"**{member}** was kicked by **{ctx.author}**!",
                fields=[("Reason", reason, False)],
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            embed = EmbedFactory.error(
                description=(
                    f"An error occurred while trying to kick {member.mention}. "
                    "Make sure my role is placed higher than the target user's role."
                )
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="ban", description="Ban a user from the server")
    @commands.guild_only()
    @checks.mod_or_permissions(ban_members=True)
    async def ban(
        self,
        ctx: Context,
        member: discord.Member,
        *,
        reason: str = "Not specified",
    ):
        """Ban a user from the server."""
        try:
            await ModerationService.ban_member(ctx, member, reason)
            embed = EmbedFactory.success(
                title="User Banned!",
                description=f"**{member}** was banned by **{ctx.author}**!",
                fields=[("Reason", reason, False)],
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            embed = EmbedFactory.error(
                description=(
                    f"An error occurred while trying to ban {member.mention}. "
                    "Make sure my role is placed higher than the target user's role."
                )
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="purge", description="Delete a number of messages")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def purge(self, ctx: Context, amount: int):
        """Delete a number of messages."""
        if amount < 1:
            embed = EmbedFactory.error(
                description=f"`{amount}` is not a valid number. Must be at least 1."
            )
            await ctx.send(embed=embed)
            return

        purged_count = await ModerationService.purge_channel(ctx.channel, amount)
        embed = EmbedFactory.success(
            title="Chat Cleared!",
            description=f"**{ctx.author}** cleared **{purged_count}** messages!",
        )
        await ctx.send(embed=embed, delete_after=5)

    @commands.hybrid_group(
        name="roles",
        aliases=["role"],
        description="Manage administrative and moderator roles for this server",
    )
    @commands.guild_only()
    async def roles(self, ctx: Context):
        """Manage administrative and moderator roles for this server."""
        if ctx.invoked_subcommand is None:
            embed = EmbedFactory.info(
                title="Server Role Configuration",
                description=(
                    "Configure administrative and moderator roles for this server:\n"
                    "• `/roles addadmin <role>` — Designate an Administrator role\n"
                    "• `/roles removeadmin <role>` — Remove an Administrator role\n"
                    "• `/roles addmod <role>` — Designate a Moderator role\n"
                    "• `/roles removemod <role>` — Remove a Moderator role\n"
                    "• `/roles list` — List all configured roles"
                ),
            )
            await ctx.send(embed=embed)

    @roles.command(name="addadmin", description="Designate an administrator role")
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def add_admin_role(self, ctx: Context, role: discord.Role):
        """Designate an administrator role for this server."""
        await self.bot.guild_repo.add_role(ctx.guild.id, role.id, "admin")
        embed = EmbedFactory.success(
            title="Role Updated",
            description=f"Successfully added {role.mention} as an **Administrator** role.",
        )
        await ctx.send(embed=embed)

    @roles.command(name="removeadmin", description="Remove a designated administrator role")
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def remove_admin_role(self, ctx: Context, role: discord.Role):
        """Remove a designated administrator role from this server."""
        removed = await self.bot.guild_repo.remove_role(ctx.guild.id, role.id, "admin")
        if not removed:
            embed = EmbedFactory.error(
                title="Error",
                description=f"{role.mention} is not registered as an Administrator role.",
            )
            await ctx.send(embed=embed)
            return
        embed = EmbedFactory.success(
            title="Role Removed",
            description=f"Successfully removed {role.mention} from Administrator roles.",
        )
        await ctx.send(embed=embed)

    @roles.command(name="addmod", description="Designate a moderator role")
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def add_mod_role(self, ctx: Context, role: discord.Role):
        """Designate a moderator role for this server."""
        await self.bot.guild_repo.add_role(ctx.guild.id, role.id, "mod")
        embed = EmbedFactory.success(
            title="Role Updated",
            description=f"Successfully added {role.mention} as a **Moderator** role.",
        )
        await ctx.send(embed=embed)

    @roles.command(name="removemod", description="Remove a designated moderator role")
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def remove_mod_role(self, ctx: Context, role: discord.Role):
        """Remove a designated moderator role from this server."""
        removed = await self.bot.guild_repo.remove_role(ctx.guild.id, role.id, "mod")
        if not removed:
            embed = EmbedFactory.error(
                title="Error",
                description=f"{role.mention} is not registered as a Moderator role.",
            )
            await ctx.send(embed=embed)
            return
        embed = EmbedFactory.success(
            title="Role Removed",
            description=f"Successfully removed {role.mention} from Moderator roles.",
        )
        await ctx.send(embed=embed)

    @roles.command(name="list", description="List configured administrator and moderator roles")
    @commands.guild_only()
    @checks.mod_or_permissions()
    async def list_roles(self, ctx: Context):
        """List configured administrator and moderator roles for this server."""
        roles_data = await self.bot.guild_repo.get_all_roles(ctx.guild.id)
        admin_roles = [
            ctx.guild.get_role(rid).mention
            for rid in roles_data.get("admin", set())
            if ctx.guild.get_role(rid)
        ]
        mod_roles = [
            ctx.guild.get_role(rid).mention
            for rid in roles_data.get("mod", set())
            if ctx.guild.get_role(rid)
        ]

        embed = EmbedFactory.create(
            title=f"Configured Roles — {ctx.guild.name}",
            fields=[
                (
                    "Administrator Roles",
                    ", ".join(admin_roles) if admin_roles else "None configured",
                    False,
                ),
                (
                    "Moderator Roles",
                    ", ".join(mod_roles) if mod_roles else "None configured",
                    False,
                ),
            ],
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    """Add Moderation commands to cogs"""
    await bot.add_cog(Moderation(bot))
