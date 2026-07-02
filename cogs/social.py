"""Social features: XP, levels, and a leaderboard (SQLite-backed).

Members earn XP by chatting (rate-limited to once a minute to stop spam).
Demonstrates the `message_content` intent + persistent storage.
"""

from __future__ import annotations

import time

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

import config
from core.database import init_db


def xp_for_level(level: int) -> int:
    """XP needed to advance FROM `level` to the next one."""
    return 5 * level**2 + 50 * level + 100


async def rank_position(db: aiosqlite.Connection, guild_id: int, level: int, xp: int) -> int:
    """1-based ladder position: how many members rank strictly above (level, xp), + 1."""
    cursor = await db.execute(
        "SELECT COUNT(*) FROM levels WHERE guild_id=? AND (level > ? OR (level = ? AND xp > ?))",
        (guild_id, level, level, xp),
    )
    row = await cursor.fetchone()
    return (row[0] if row else 0) + 1


class Social(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._cooldowns: dict[tuple[int, int], float] = {}

    async def cog_load(self) -> None:
        await init_db()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        key = (message.guild.id, message.author.id)
        now = time.time()
        if now - self._cooldowns.get(key, 0.0) < 60:  # one XP grant per minute
            return
        self._cooldowns[key] = now
        await self._grant_xp(message, key)

    async def _grant_xp(self, message: discord.Message, key: tuple[int, int]) -> None:
        guild_id, user_id = key
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT xp, level FROM levels WHERE guild_id=? AND user_id=?", key
            )
            row = await cursor.fetchone()
            xp, level = row if row else (0, 0)

            xp += 15
            leveled_up = False
            while xp >= xp_for_level(level):
                xp -= xp_for_level(level)
                level += 1
                leveled_up = True

            await db.execute(
                "INSERT INTO levels (guild_id, user_id, xp, level) VALUES (?,?,?,?) "
                "ON CONFLICT(guild_id, user_id) "
                "DO UPDATE SET xp=excluded.xp, level=excluded.level",
                (guild_id, user_id, xp, level),
            )
            await db.commit()

        if leveled_up:
            # Let other cogs (e.g. roles) react to milestones.
            self.bot.dispatch("level_up", message.author, level)
            await message.channel.send(
                f"🎉 {message.author.mention} reached **level {level}**!", delete_after=15
            )

    @commands.hybrid_command(description="Show your (or someone's) level and XP.")
    @app_commands.describe(member="Whose rank to show (defaults to you).")
    @commands.guild_only()
    async def rank(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        assert ctx.guild is not None
        member = member or ctx.author  # type: ignore[assignment]
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT xp, level FROM levels WHERE guild_id=? AND user_id=?",
                (ctx.guild.id, member.id),
            )
            row = await cursor.fetchone()
            if row is not None:
                xp, level = row
                position = await rank_position(db, ctx.guild.id, level, xp)
            else:
                xp, level, position = 0, 0, None
        embed = discord.Embed(title=f"{member.display_name}'s Rank", color=config.COLOR)
        embed.set_thumbnail(url=member.display_avatar.url)
        if position is not None:
            embed.add_field(name="Rank", value=f"#{position}")
        embed.add_field(name="Level", value=str(level))
        embed.add_field(name="XP", value=f"{xp} / {xp_for_level(level)}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Show the server XP leaderboard.")
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context) -> None:
        assert ctx.guild is not None
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT user_id, level, xp FROM levels WHERE guild_id=? "
                "ORDER BY level DESC, xp DESC LIMIT 10",
                (ctx.guild.id,),
            )
            rows = await cursor.fetchall()
            if not rows:
                await ctx.send("No XP earned yet — start chatting!", ephemeral=True)
                return
            lines = [
                f"**{i}.** <@{uid}> — level {lvl} ({xp} XP)"
                for i, (uid, lvl, xp) in enumerate(rows, 1)
            ]
            # If the caller isn't in the top 10, show where they stand.
            if ctx.author.id not in {uid for uid, _, _ in rows}:
                cursor = await db.execute(
                    "SELECT level, xp FROM levels WHERE guild_id=? AND user_id=?",
                    (ctx.guild.id, ctx.author.id),
                )
                me = await cursor.fetchone()
                if me is not None:
                    position = await rank_position(db, ctx.guild.id, me[0], me[1])
                    lines.append(
                        f"\n**{position}.** {ctx.author.mention} — "
                        f"level {me[0]} ({me[1]} XP) *(you)*"
                    )
        embed = discord.Embed(
            title="🏆 Leaderboard", description="\n".join(lines), color=config.COLOR
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Social(bot))
