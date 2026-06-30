"""Gaming utilities: native polls, dice, trivia, and an LFG board.

- /poll       — create a native Discord poll.
- /roll       — dice roller with NdM(+/-K) notation (e.g. 2d6, d20, 3d8+2).
- /trivia     — a multiple-choice question (Open Trivia DB) with answer buttons.
- /lfg        — a "looking for group" board with Join/Leave buttons.
"""

from __future__ import annotations

import datetime
import html
import random
import re

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

import config

_DICE_RE = re.compile(r"^(\d*)d(\d+)([+-]\d+)?$", re.IGNORECASE)
_TRIVIA_URL = "https://opentdb.com/api.php?amount=1&type=multiple"
_LETTERS = ("A", "B", "C", "D", "E", "F")


# ── Trivia ────────────────────────────────────────────────────
class TriviaButton(discord.ui.Button):
    def __init__(self, letter: str, correct: bool) -> None:
        super().__init__(label=letter, style=discord.ButtonStyle.primary)
        self.correct = correct

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TriviaView = self.view  # type: ignore[assignment]
        if view.answered:
            await interaction.response.send_message("Someone already solved it!", ephemeral=True)
            return
        if not self.correct:
            await interaction.response.send_message("❌ Not quite — try again!", ephemeral=True)
            return
        view.answered = True
        for child in view.children:
            child.disabled = True
            if isinstance(child, TriviaButton) and child.correct:
                child.style = discord.ButtonStyle.success
        view.embed.add_field(
            name="Solved!",
            value=f"✅ {interaction.user.mention} — **{view.correct_answer}**",
            inline=False,
        )
        await interaction.response.edit_message(embed=view.embed, view=view)


class TriviaView(discord.ui.View):
    def __init__(
        self, num_answers: int, correct_index: int, correct_answer: str, embed: discord.Embed
    ) -> None:
        super().__init__(timeout=45)
        self.correct_answer = correct_answer
        self.embed = embed
        self.answered = False
        for i in range(num_answers):
            self.add_item(TriviaButton(_LETTERS[i], i == correct_index))


# ── LFG ───────────────────────────────────────────────────────
class LFGView(discord.ui.View):
    def __init__(self, game: str, slots: int, host: discord.abc.User) -> None:
        super().__init__(timeout=3600)
        self.game = game
        self.slots = slots
        self.players: dict[int, str] = {host.id: host.display_name}

    def embed(self) -> discord.Embed:
        roster = "\n".join(f"• {name}" for name in self.players.values()) or "_empty_"
        embed = discord.Embed(title=f"🎮 LFG: {self.game}", description=roster, color=config.COLOR)
        full = " — **FULL**" if len(self.players) >= self.slots else ""
        embed.set_footer(text=f"{len(self.players)}/{self.slots} players{full}")
        return embed

    @discord.ui.button(label="Join", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        uid = interaction.user.id
        if uid in self.players:
            await interaction.response.send_message("You're already in.", ephemeral=True)
            return
        if len(self.players) >= self.slots:
            await interaction.response.send_message("Sorry, it's full.", ephemeral=True)
            return
        self.players[uid] = interaction.user.display_name
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.secondary)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.players.pop(interaction.user.id, None) is None:
            await interaction.response.send_message("You're not in this group.", ephemeral=True)
            return
        await interaction.response.edit_message(embed=self.embed(), view=self)


class Gaming(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(description="Create a poll.")
    @app_commands.describe(
        question="The poll question",
        options="Answers separated by `|` (2-10)",
        hours="How long the poll runs (1-168)",
    )
    async def poll(
        self,
        interaction: discord.Interaction,
        question: str,
        options: str,
        hours: app_commands.Range[int, 1, 168] = 24,
    ) -> None:
        answers = [o.strip() for o in options.split("|") if o.strip()][:10]
        if len(answers) < 2:
            await interaction.response.send_message(
                "Give at least 2 options separated by `|` — e.g. `Valorant | Minecraft`.",
                ephemeral=True,
            )
            return
        poll = discord.Poll(question=question[:300], duration=datetime.timedelta(hours=hours))
        for answer in answers:
            poll.add_answer(text=answer[:55])
        await interaction.response.send_message(poll=poll)

    @app_commands.command(description="Roll dice, e.g. 2d6, d20, 3d8+2.")
    @app_commands.describe(dice="Dice notation like 2d6, d20, or 3d8+2")
    async def roll(self, interaction: discord.Interaction, dice: str = "1d6") -> None:
        match = _DICE_RE.match(dice.strip().replace(" ", ""))
        if match is None:
            await interaction.response.send_message(
                "Couldn't parse that — try `2d6`, `d20`, or `3d8+2`.", ephemeral=True
            )
            return
        count = int(match[1]) if match[1] else 1
        sides = int(match[2])
        modifier = int(match[3]) if match[3] else 0
        if not (1 <= count <= 100 and 2 <= sides <= 1000):
            await interaction.response.send_message(
                "Keep it to 1-100 dice with 2-1000 sides.", ephemeral=True
            )
            return
        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls) + modifier
        breakdown = " + ".join(map(str, rolls))
        if modifier:
            breakdown += f" {'+' if modifier > 0 else '-'} {abs(modifier)}"
        embed = discord.Embed(
            title=f"🎲 {dice}", description=f"# {total}\n`{breakdown}`", color=config.COLOR
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(description="Get a trivia question.")
    async def trivia(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.get(_TRIVIA_URL) as resp,
            ):
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError):
            await interaction.followup.send(
                "Couldn't reach the trivia service — try again shortly.", ephemeral=True
            )
            return
        if data.get("response_code") != 0 or not data.get("results"):
            await interaction.followup.send("No trivia available right now.", ephemeral=True)
            return

        q = data["results"][0]
        question = html.unescape(q["question"])
        correct = html.unescape(q["correct_answer"])
        answers = [html.unescape(a) for a in q["incorrect_answers"]] + [correct]
        random.shuffle(answers)
        correct_index = answers.index(correct)
        listing = "\n".join(f"{_LETTERS[i]}) {a}" for i, a in enumerate(answers))
        embed = discord.Embed(
            title=f"🧠 Trivia · {html.unescape(q['category'])}",
            description=f"**{question}**\n\n{listing}",
            color=config.COLOR,
        )
        embed.set_footer(text=f"Difficulty: {q['difficulty'].title()}")
        view = TriviaView(len(answers), correct_index, correct, embed)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(description="Start a 'looking for group' board.")
    @app_commands.describe(game="What you're playing", slots="Total players you need (2-25)")
    async def lfg(
        self,
        interaction: discord.Interaction,
        game: str,
        slots: app_commands.Range[int, 2, 25] = 5,
    ) -> None:
        view = LFGView(game[:100], slots, interaction.user)
        await interaction.response.send_message(embed=view.embed(), view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Gaming(bot))
