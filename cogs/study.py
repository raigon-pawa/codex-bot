"""Study tools: pomodoro timers, reminders, and flashcards.

- /pomodoro start|stop — a focus timer that pings you at the work→break→done
  transitions. In-memory, so a restart cancels any running timers.
- /remindme + /reminders — schedule reminders; stored in SQLite so they survive
  restarts, dispatched by a background `tasks.loop`.
- /flashcards add|review|list|delete — a personal flashcard deck per server.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import re
import time

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from core.database import init_db

_DURATION_RE = re.compile(r"(\d+)\s*([smhd])", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
MAX_DURATION = 30 * 86400  # 30 days


def parse_duration(text: str) -> int | None:
    """Parse '10m', '1h30m', '2d', '45s' into seconds. None if invalid/out of range."""
    matches = _DURATION_RE.findall(text)
    if not matches:
        return None
    total = sum(int(n) * _UNIT_SECONDS[unit.lower()] for n, unit in matches)
    return total if 0 < total <= MAX_DURATION else None


class RevealView(discord.ui.View):
    """A single 'Reveal answer' button for flashcard review."""

    def __init__(self, back: str) -> None:
        super().__init__(timeout=120)
        self._back = back

    @discord.ui.button(label="Reveal answer", style=discord.ButtonStyle.primary, emoji="💡")
    async def reveal(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        button.disabled = True
        embed = interaction.message.embeds[0]
        embed.add_field(name="Answer", value=self._back[:1024], inline=False)
        await interaction.response.edit_message(embed=embed, view=self)


class Study(commands.Cog):
    pomodoro = app_commands.Group(name="pomodoro", description="Focus timers.")
    flashcards = app_commands.Group(name="flashcards", description="Personal flashcard decks.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._timers: dict[int, asyncio.Task] = {}  # user_id -> running pomodoro task

    async def cog_load(self) -> None:
        await init_db()
        self.reminder_loop.start()

    async def cog_unload(self) -> None:
        self.reminder_loop.cancel()
        for task in self._timers.values():
            task.cancel()

    # ── Pomodoro ──────────────────────────────────────────────
    @pomodoro.command(name="start", description="Start a focus timer.")
    @app_commands.describe(work="Focus minutes (default 25)", rest="Break minutes (default 5)")
    async def pomodoro_start(
        self,
        interaction: discord.Interaction,
        work: app_commands.Range[int, 1, 180] = 25,
        rest: app_commands.Range[int, 1, 60] = 5,
    ) -> None:
        if interaction.channel is None:
            return
        if interaction.user.id in self._timers:
            await interaction.response.send_message(
                "You already have a timer running — `/pomodoro stop` it first.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"🍅 Focus for **{work} min** — I'll ping you when it's break time."
        )
        self._timers[interaction.user.id] = asyncio.create_task(
            self._run_pomodoro(interaction.channel, interaction.user, work, rest)
        )

    async def _run_pomodoro(
        self, channel: discord.abc.Messageable, user: discord.abc.User, work: int, rest: int
    ) -> None:
        try:
            await asyncio.sleep(work * 60)
            await channel.send(f"{user.mention} ☕ Time for a **{rest} min** break!")
            await asyncio.sleep(rest * 60)
            await channel.send(f"{user.mention} 🍅 Break's over — back to it!")
        except asyncio.CancelledError:
            return
        finally:
            self._timers.pop(user.id, None)

    @pomodoro.command(name="stop", description="Cancel your focus timer.")
    async def pomodoro_stop(self, interaction: discord.Interaction) -> None:
        task = self._timers.pop(interaction.user.id, None)
        if task is None:
            await interaction.response.send_message("No timer running.", ephemeral=True)
            return
        task.cancel()
        await interaction.response.send_message("🛑 Timer cancelled.", ephemeral=True)

    # ── Reminders ─────────────────────────────────────────────
    @app_commands.command(description="Remind you after a delay, e.g. 10m, 1h30m, 2d.")
    @app_commands.describe(when="When (e.g. 10m, 1h30m, 2d)", text="What to remind you about")
    async def remindme(self, interaction: discord.Interaction, when: str, text: str) -> None:
        seconds = parse_duration(when)
        if seconds is None:
            await interaction.response.send_message(
                "Couldn't parse that time. Try `10m`, `1h30m`, or `2d` (max 30d).", ephemeral=True
            )
            return
        async with aiosqlite.connect(config.DB_PATH) as db:
            await db.execute(
                "INSERT INTO reminders (user_id, channel_id, remind_at, message) VALUES (?,?,?,?)",
                (interaction.user.id, interaction.channel_id, time.time() + seconds, text),
            )
            await db.commit()
        due = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
        await interaction.response.send_message(
            f"⏰ Got it — I'll remind you {discord.utils.format_dt(due, 'R')}: {text}"
        )

    @app_commands.command(description="List your pending reminders.")
    async def reminders(self, interaction: discord.Interaction) -> None:
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT remind_at, message FROM reminders WHERE user_id=? ORDER BY remind_at",
                (interaction.user.id,),
            )
            rows = await cursor.fetchall()
        if not rows:
            await interaction.response.send_message("No pending reminders.", ephemeral=True)
            return
        lines = [
            f"• {discord.utils.format_dt(datetime.datetime.fromtimestamp(at, datetime.UTC), 'R')}"
            f" — {msg}"
            for at, msg in rows
        ]
        embed = discord.Embed(
            title="⏰ Your reminders", description="\n".join(lines)[:4096], color=config.COLOR
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tasks.loop(seconds=30)
    async def reminder_loop(self) -> None:
        now = time.time()
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id, user_id, channel_id, message FROM reminders WHERE remind_at <= ?",
                (now,),
            )
            for rid, user_id, channel_id, message in await cursor.fetchall():
                channel = self.bot.get_channel(channel_id)
                if isinstance(channel, discord.abc.Messageable):
                    with contextlib.suppress(discord.HTTPException):
                        await channel.send(f"<@{user_id}> ⏰ Reminder: {message}")
                await db.execute("DELETE FROM reminders WHERE id=?", (rid,))
            await db.commit()

    @reminder_loop.before_loop
    async def _before_reminders(self) -> None:
        await self.bot.wait_until_ready()

    # ── Flashcards ────────────────────────────────────────────
    @flashcards.command(name="add", description="Add a flashcard to your deck.")
    @app_commands.describe(front="The prompt / question", back="The answer")
    @app_commands.guild_only()
    async def flashcards_add(self, interaction: discord.Interaction, front: str, back: str) -> None:
        async with aiosqlite.connect(config.DB_PATH) as db:
            await db.execute(
                "INSERT INTO flashcards (guild_id, user_id, front, back, created_at) "
                "VALUES (?,?,?,?,?)",
                (interaction.guild_id, interaction.user.id, front, back, time.time()),
            )
            await db.commit()
        await interaction.response.send_message("✅ Card added to your deck.", ephemeral=True)

    @flashcards.command(name="review", description="Review a random flashcard.")
    @app_commands.guild_only()
    async def flashcards_review(self, interaction: discord.Interaction) -> None:
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT front, back FROM flashcards WHERE guild_id=? AND user_id=? "
                "ORDER BY RANDOM() LIMIT 1",
                (interaction.guild_id, interaction.user.id),
            )
            row = await cursor.fetchone()
        if row is None:
            await interaction.response.send_message(
                "Your deck is empty — add cards with `/flashcards add`.", ephemeral=True
            )
            return
        front, back = row
        embed = discord.Embed(title="🃏 Flashcard", description=front[:4096], color=config.COLOR)
        await interaction.response.send_message(embed=embed, view=RevealView(back), ephemeral=True)

    @flashcards.command(name="list", description="List your flashcards.")
    @app_commands.guild_only()
    async def flashcards_list(self, interaction: discord.Interaction) -> None:
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id, front FROM flashcards WHERE guild_id=? AND user_id=? ORDER BY id",
                (interaction.guild_id, interaction.user.id),
            )
            rows = await cursor.fetchall()
        if not rows:
            await interaction.response.send_message("Your deck is empty.", ephemeral=True)
            return
        lines = [f"`{cid}` — {front[:80]}" for cid, front in rows]
        embed = discord.Embed(
            title="🃏 Your flashcards", description="\n".join(lines)[:4096], color=config.COLOR
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @flashcards.command(name="delete", description="Delete a flashcard by ID.")
    @app_commands.describe(card_id="The card's ID (from /flashcards list)")
    @app_commands.guild_only()
    async def flashcards_delete(self, interaction: discord.Interaction, card_id: int) -> None:
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "DELETE FROM flashcards WHERE id=? AND guild_id=? AND user_id=?",
                (card_id, interaction.guild_id, interaction.user.id),
            )
            await db.commit()
            deleted = cursor.rowcount
        await interaction.response.send_message(
            "🗑️ Card deleted." if deleted else "No card with that ID in your deck.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Study(bot))
