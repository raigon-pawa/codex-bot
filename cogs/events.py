"""Gateway event listeners: welcome & goodbye messages.

Demonstrates the privileged `members` intent. Posts to the server's configured
System Channel; later you can store a custom channel in `guild_config`.
"""

from __future__ import annotations

import discord
from discord.ext import commands

import config


class Events(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _system_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        channel = guild.system_channel
        if channel and channel.permissions_for(guild.me).send_messages:
            return channel
        return None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        channel = self._system_channel(member.guild)
        if channel is None:
            return
        embed = discord.Embed(
            description=f"Welcome to **{member.guild.name}**, {member.mention}! 🎉",
            color=config.COLOR,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"You are member #{member.guild.member_count}")
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        channel = self._system_channel(member.guild)
        if channel is None:
            return
        await channel.send(f"**{member}** has left the server. 👋")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Events(bot))
