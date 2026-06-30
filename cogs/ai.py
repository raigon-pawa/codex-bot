"""AI assistance powered by Claude (Anthropic).

Provides /ask and /summarize. Uses the **async** Anthropic client so API calls
never block the bot's event loop. Requires ANTHROPIC_API_KEY in the environment;
without it the commands respond with a friendly "not configured" message.

Model choice lives in config (AI_MODEL). We omit the `thinking` parameter so
replies stay fast and cheap for chat — and the system prompt asks for a direct
final answer, since Opus 4.8 can otherwise spill reasoning into the reply when
thinking is off.
"""

from __future__ import annotations

import anthropic
import discord
from discord import app_commands
from discord.ext import commands

import config

EMBED_LIMIT = 4096  # Discord embed description hard limit

ASK_SYSTEM = (
    "You are Codex, a friendly, knowledgeable Discord assistant for a community of "
    "students and gamers. Answer directly and concisely: give the final answer only, "
    "with no exploratory reasoning or preamble. Keep replies under ~1500 characters "
    "so they fit a Discord message, and use Discord markdown (`code`, **bold**, "
    "lists) where it helps."
)

SUMMARY_SYSTEM = (
    "You summarise Discord conversations. Produce a tight bullet-point summary of the "
    "key topics, decisions, and open questions. Be concise and neutral. Output only "
    "the summary."
)

NOT_CONFIGURED = "AI features aren't configured yet (missing `ANTHROPIC_API_KEY`)."


class AI(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # AsyncAnthropic also reads ANTHROPIC_API_KEY from the env; we pass it
        # explicitly from config (which already loaded .env) to be unambiguous.
        self.client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

    async def _complete(self, *, system: str, user: str) -> str:
        message = await self.client.messages.create(
            model=config.AI_MODEL,
            max_tokens=config.AI_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # response.content is a list of blocks; gather the text ones.
        text = "".join(b.text for b in message.content if b.type == "text").strip()
        return text or "*(no response)*"

    @app_commands.command(description="Ask Codex's AI assistant a question.")
    @app_commands.describe(question="What do you want to ask?")
    @app_commands.checks.cooldown(1, 15.0)  # 1 use / 15s per user — caps spam & cost
    async def ask(self, interaction: discord.Interaction, question: str) -> None:
        if not config.ANTHROPIC_API_KEY:
            await interaction.response.send_message(NOT_CONFIGURED, ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        answer = await self._complete(system=ASK_SYSTEM, user=question)
        embed = discord.Embed(description=answer[:EMBED_LIMIT], color=config.COLOR)
        embed.set_author(
            name=f"Asked by {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url,
        )
        embed.set_footer(text=f"Codex AI · {config.AI_MODEL}")
        await interaction.followup.send(content=f"> {question[:256]}", embed=embed)

    @app_commands.command(description="Summarise the recent conversation in this channel.")
    @app_commands.describe(messages="How many recent messages to summarise (5-100).")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 30.0)
    async def summarize(
        self,
        interaction: discord.Interaction,
        messages: app_commands.Range[int, 5, 100] = 30,
    ) -> None:
        if not config.ANTHROPIC_API_KEY:
            await interaction.response.send_message(NOT_CONFIGURED, ephemeral=True)
            return
        if interaction.channel is None:
            return
        await interaction.response.defer(thinking=True)

        history: list[str] = []
        async for msg in interaction.channel.history(limit=messages):
            if msg.author.bot or not msg.content:
                continue
            history.append(f"{msg.author.display_name}: {msg.content}")
        history.reverse()  # oldest first

        if not history:
            await interaction.followup.send("Nothing to summarise here yet.", ephemeral=True)
            return

        transcript = "\n".join(history)[:8000]  # keep the prompt bounded
        answer = await self._complete(
            system=SUMMARY_SYSTEM,
            user=f"Summarise this conversation:\n\n{transcript}",
        )
        embed = discord.Embed(
            title=f"📝 Summary of the last {len(history)} messages",
            description=answer[:EMBED_LIMIT],
            color=config.COLOR,
        )
        embed.set_footer(text=f"Codex AI · {config.AI_MODEL}")
        await interaction.followup.send(embed=embed)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.CommandOnCooldown):
            msg = f"Slow down — try again in {error.retry_after:.0f}s."
        elif isinstance(error, app_commands.CommandInvokeError) and isinstance(
            error.original, anthropic.APIError
        ):
            msg = _api_error_message(error.original)
        else:
            msg = f"Something went wrong: {error}"

        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


def _api_error_message(error: anthropic.APIError) -> str:
    if isinstance(error, anthropic.RateLimitError):
        return "The AI is rate-limited right now — please try again shortly."
    if isinstance(error, anthropic.AuthenticationError):
        return "AI isn't configured correctly (authentication failed)."
    if isinstance(error, anthropic.APIConnectionError):
        return "Couldn't reach the AI service — please try again."
    return "The AI service returned an error — please try again."


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AI(bot))
