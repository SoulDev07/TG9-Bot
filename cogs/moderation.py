"""Stores moderation commands of Bot"""

import discord
from discord.ext import commands
from discord.ext.commands import Context

from helpers import checks, exceptions


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
        embed = discord.Embed(
            description=sentence,
            color=0x42F56C,
        )
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
        checks.check_hierarchy(ctx, member)

        embed = discord.Embed(
            title="User Warned!",
            description=f"**{member}** was warned by **{ctx.author}**!",
            color=0x42F56C,
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.send(embed=embed)
        try:
            await member.send(
                f"You were warned in **{ctx.guild.name}** by **{ctx.author}**!\nReason: {reason}"
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def kick_ban_common(
        self,
        ctx: Context,
        member: discord.Member,
        action: str,
        reason: str,
    ):
        """Common logic for kick and ban commands with role hierarchy enforcement."""
        checks.check_hierarchy(ctx, member)
        action_verb = "kicked" if action == "kick" else "banned"
        audit_reason = checks.get_audit_reason(ctx.author, reason)

        try:
            await member.send(
                f"You were {action_verb} from **{ctx.guild.name}** by **{ctx.author}**!\n"
                f"Reason: {reason}"
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

        try:
            if action == "kick":
                await member.kick(reason=audit_reason)
            elif action == "ban":
                await member.ban(reason=audit_reason)

            embed = discord.Embed(
                title=f"User {action.capitalize()}!",
                description=f"**{member}** was {action_verb} by **{ctx.author}**!",
                color=0x42F56C,
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            await ctx.send(embed=embed)

        except discord.Forbidden:
            embed = discord.Embed(
                title="Error!",
                description=(
                    f"An error occurred while trying to {action} {member.mention}. "
                    "Make sure my role is placed higher than the target user's role."
                ),
                color=0xE02B2B,
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
        await self.kick_ban_common(ctx, member, "kick", reason)

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
        await self.kick_ban_common(ctx, member, "ban", reason)

    @commands.hybrid_command(name="purge", description="Delete a number of messages")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def purge(self, ctx: Context, amount: int):
        """Delete a number of messages."""
        if amount < 1:
            embed = discord.Embed(
                title="Error!",
                description=f"`{amount}` is not a valid number. Must be at least 1.",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)
            return

        purged_messages = await ctx.channel.purge(limit=amount)
        embed = discord.Embed(
            title="Chat Cleared!",
            description=(f"**{ctx.author}** cleared **{len(purged_messages)}** messages!"),
            color=0x42F56C,
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
            embed = discord.Embed(
                title="Server Role Configuration",
                description=(
                    "Configure administrative and moderator roles for this server:\n"
                    "• `/roles addadmin <role>` — Designate an Administrator role\n"
                    "• `/roles removeadmin <role>` — Remove an Administrator role\n"
                    "• `/roles addmod <role>` — Designate a Moderator role\n"
                    "• `/roles removemod <role>` — Remove a Moderator role\n"
                    "• `/roles list` — List all configured roles"
                ),
                color=0x42F56C,
            )
            await ctx.send(embed=embed)

    @roles.command(name="addadmin", description="Designate an administrator role")
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def add_admin_role(self, ctx: Context, role: discord.Role):
        """Designate an administrator role for this server."""
        await self.bot.guild_repo.add_role(ctx.guild.id, role.id, "admin")
        embed = discord.Embed(
            title="Role Updated",
            description=f"Successfully added {role.mention} as an **Administrator** role.",
            color=0x42F56C,
        )
        await ctx.send(embed=embed)

    @roles.command(name="removeadmin", description="Remove a designated administrator role")
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def remove_admin_role(self, ctx: Context, role: discord.Role):
        """Remove a designated administrator role from this server."""
        removed = await self.bot.guild_repo.remove_role(ctx.guild.id, role.id, "admin")
        if not removed:
            embed = discord.Embed(
                title="Error",
                description=f"{role.mention} is not registered as an Administrator role.",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)
            return
        embed = discord.Embed(
            title="Role Removed",
            description=f"Successfully removed {role.mention} from Administrator roles.",
            color=0x42F56C,
        )
        await ctx.send(embed=embed)

    @roles.command(name="addmod", description="Designate a moderator role")
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def add_mod_role(self, ctx: Context, role: discord.Role):
        """Designate a moderator role for this server."""
        await self.bot.guild_repo.add_role(ctx.guild.id, role.id, "mod")
        embed = discord.Embed(
            title="Role Updated",
            description=f"Successfully added {role.mention} as a **Moderator** role.",
            color=0x42F56C,
        )
        await ctx.send(embed=embed)

    @roles.command(name="removemod", description="Remove a designated moderator role")
    @commands.guild_only()
    @checks.admin_or_permissions(administrator=True)
    async def remove_mod_role(self, ctx: Context, role: discord.Role):
        """Remove a designated moderator role from this server."""
        removed = await self.bot.guild_repo.remove_role(ctx.guild.id, role.id, "mod")
        if not removed:
            embed = discord.Embed(
                title="Error",
                description=f"{role.mention} is not registered as a Moderator role.",
                color=0xE02B2B,
            )
            await ctx.send(embed=embed)
            return
        embed = discord.Embed(
            title="Role Removed",
            description=f"Successfully removed {role.mention} from Moderator roles.",
            color=0x42F56C,
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

        embed = discord.Embed(
            title=f"Configured Roles — {ctx.guild.name}",
            color=0x42F56C,
        )
        embed.add_field(
            name="Administrator Roles",
            value=", ".join(admin_roles) if admin_roles else "None configured",
            inline=False,
        )
        embed.add_field(
            name="Moderator Roles",
            value=", ".join(mod_roles) if mod_roles else "None configured",
            inline=False,
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    """Add Moderation commands to cogs"""
    await bot.add_cog(Moderation(bot))
