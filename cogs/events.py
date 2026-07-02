"""Gateway event listeners: welcome & goodbye messages.

Uses the privileged `members` intent. Posts to the channel configured with
`/welcome set` (stored in `guild_config.welcome_channel`), falling back to the
server's System Channel. `/welcome disable` turns the announcements off.
"""

from __future__ import annotations

import aiosqlite
import discord
from discord.ext import commands

import config
from core.database import init_db

_DISABLED = 0  # welcome_channel sentinel meaning "announcements off"


class Events(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await init_db()

    def _system_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        channel = guild.system_channel
        if channel and channel.permissions_for(guild.me).send_messages:
            return channel
        return None

    async def _announce_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """The configured welcome channel, or the System Channel by default.

        `NULL` → System Channel (default); `0` → disabled; an id → that channel
        (falling back to the System Channel if it's gone or unwritable)."""
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT welcome_channel FROM guild_config WHERE guild_id=?", (guild.id,)
            )
            row = await cursor.fetchone()
        configured = row[0] if row else None
        if configured == _DISABLED:
            return None
        if configured:
            channel = guild.get_channel(configured)
            if (
                isinstance(channel, discord.TextChannel)
                and channel.permissions_for(guild.me).send_messages
            ):
                return channel
        return self._system_channel(guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        channel = await self._announce_channel(member.guild)
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
        channel = await self._announce_channel(member.guild)
        if channel is None:
            return
        await channel.send(f"**{member}** has left the server. 👋")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Events(bot))
