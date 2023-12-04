"""Stores general commands of Bot"""

import discord
from discord.ext import commands
from discord.ext.commands import Context

BOT_VERSION = "Ver 1.4"


class General(commands.Cog, name="general"):
    """General Commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="info", aliases=["botinfo"], description="Get info about Bot")
    async def info(self, ctx: Context):
        """Get information about the Bot"""

        embed = discord.Embed(description="Made by SoulDev07", color=0x42F56C)
        embed.set_author(name="Bot Information")
        embed.add_field(name="Owner:", value="TheGriffin999", inline=False)
        embed.add_field(name="Bot Version:", value=BOT_VERSION, inline=False)
        embed.add_field(name="Prefix:", value=str(self.bot.config["bot_prefix"]), inline=False)
        embed.set_footer(text=f"Requested by {ctx.author}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ping", description="Get Bot ping")
    async def ping(self, ctx):
        """Check if the bot is alive."""

        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"The bot latency is {round(self.bot.latency * 1000)}ms.",
            color=0x42F56C
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="server", aliases=["support", "supportserver"], description="Get support Server")
    async def server(self, ctx):
        """Get the invite link of the discord server of the bot for some support."""

        server_link = self.bot.config["bot_invite_link"]
        embed = discord.Embed(description=f"Join the support server for the bot by clicking [here]({server_link}).", color=0xD75BF4)
        try:
            await ctx.author.send(embed=embed)
            await ctx.send("I sent you a private message!")
        except discord.Forbidden:
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="poll", description="Generate a poll")
    @commands.guild_only()
    async def poll(self, ctx, *, title: str):
        """Create a poll where members can vote."""

        embed = discord.Embed(
            title="A new poll has been created!",
            description=f"{title}",
            color=0x42F56C
        )
        embed.set_footer(
            text=f"Poll created by: {ctx.author} • React to vote!")
        embed_message = await ctx.send(embed=embed)
        await embed_message.add_reaction("👍")
        await embed_message.add_reaction("👎")
        await embed_message.add_reaction("🤷")


async def setup(bot: commands.Bot):
    """Add General commands to cogs"""
    await bot.add_cog(General(bot))
