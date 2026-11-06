"""Help command for TG9 Bot."""

from discord.ext import commands

from helpers.embeds import EmbedFactory


class Help(commands.Cog, name="help"):
    """Help Commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="List all available commands")
    async def help(self, ctx):
        """List all commands from every loaded cog."""
        prefix = getattr(self.bot.config, "bot_prefix", "Tg9 ")

        embed = EmbedFactory.success(
            title="Help",
            description="List of available commands:",
        )

        for cog_name in self.bot.cogs:
            cog = self.bot.get_cog(cog_name)
            if not cog:
                continue
            bot_commands = cog.get_commands()
            command_list = [command.name for command in bot_commands]
            command_description = [command.help for command in bot_commands]

            help_text = "\n".join(
                f"```{prefix}{n} - {h}```"
                for n, h in zip(command_list, command_description, strict=False)
            )
            embed.add_field(name=cog_name.capitalize(), value=help_text, inline=False)

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    """Register Help cog."""
    await bot.add_cog(Help(bot))
