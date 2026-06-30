"""AI assistance powered by Claude (Anthropic).

Commands:
  /ask       — one-off question (single-turn; cheapest, no caching).
  /chat      — multi-turn conversation that REMEMBERS context, with prompt
               caching on the growing history so each follow-up re-reads it at
               ~0.1x input cost.
  /endchat   — clear your conversation.
  /summarize — bullet summary of recent channel messages.

Uses the async Anthropic client so API calls never block the event loop.

Prompt-caching note: a cache only forms once the cached prefix passes the model
minimum (4096 tokens on Opus/Haiku, 2048 on Sonnet). So /ask and /summarize stay
uncached — tiny, non-repeating prompts have nothing to reuse, and marking them
would just pay the cache-write premium for zero reads. /chat caches the history,
which is exactly the repeated-prefix case caching is built for. Each reply's
footer shows token usage (and `cached` tokens once it kicks in); see also logs.
"""

from __future__ import annotations

import logging
import time

import anthropic
import discord
from discord import app_commands
from discord.ext import commands

import config

log = logging.getLogger("codex.ai")

EMBED_LIMIT = 4096  # Discord embed description hard limit
MAX_HISTORY = 24  # cap stored messages (~12 turns) to bound input tokens
SESSION_TTL = 1800.0  # forget an idle conversation after 30 minutes

ASK_SYSTEM = (
    "You are Codex, a friendly, knowledgeable Discord assistant for a community of "
    "students and gamers. Answer directly and concisely: give the final answer only, "
    "with no exploratory reasoning or preamble. Keep replies under ~1500 characters "
    "so they fit a Discord message, and use Discord markdown (`code`, **bold**, "
    "lists) where it helps."
)

CHAT_SYSTEM = (
    "You are Codex, a friendly, knowledgeable Discord assistant for a community of "
    "students and gamers. You're in an ongoing conversation — use the earlier turns "
    "for context. Be concise and helpful, keep replies under ~1500 characters, and "
    "use Discord markdown where it helps."
)

SUMMARY_SYSTEM = (
    "You summarise Discord conversations. Produce a tight bullet-point summary of the "
    "key topics, decisions, and open questions. Be concise and neutral. Output only "
    "the summary."
)

NOT_CONFIGURED = "AI features aren't configured yet (missing `ANTHROPIC_API_KEY`)."


def _fmt_usage(usage: anthropic.types.Usage) -> str:
    # Always report `cached` so the footer never goes silent on cache info — it
    # reads 0 until a conversation's prefix passes the model's cache minimum.
    cached = getattr(usage, "cache_read_input_tokens", 0) or 0
    return f"{usage.input_tokens} in · {usage.output_tokens} out · {cached} cached"


class AI(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # AsyncAnthropic also reads ANTHROPIC_API_KEY from the env; we pass it
        # explicitly from config (which already loaded .env) to be unambiguous.
        self.client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
        # (channel_id, user_id) -> {"messages": list, "ts": float}
        self._chats: dict[tuple[int, int], dict] = {}

    # ── Claude call ───────────────────────────────────────────
    async def _complete(
        self, *, system: str, messages: list[dict], cache: bool = False
    ) -> tuple[str, anthropic.types.Usage]:
        api_messages = self._with_cache_breakpoint(messages) if cache else messages
        message = await self.client.messages.create(
            model=config.AI_MODEL,
            max_tokens=config.AI_MAX_TOKENS,
            system=system,
            messages=api_messages,
        )
        u = message.usage
        log.info(
            "ai model=%s in=%s out=%s cache_write=%s cache_read=%s",
            config.AI_MODEL,
            u.input_tokens,
            u.output_tokens,
            getattr(u, "cache_creation_input_tokens", 0),
            getattr(u, "cache_read_input_tokens", 0),
        )
        text = "".join(b.text for b in message.content if b.type == "text").strip()
        return text or "*(no response)*", u

    @staticmethod
    def _with_cache_breakpoint(messages: list[dict]) -> list[dict]:
        """Put a `cache_control` breakpoint on the last message block. Caching is a
        prefix match, so this caches everything before it (system + prior turns);
        the next turn re-reads that prefix at ~0.1x cost."""
        out = [dict(m) for m in messages[:-1]]
        last = messages[-1]
        out.append(
            {
                "role": last["role"],
                "content": [
                    {
                        "type": "text",
                        "text": last["content"],
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }
        )
        return out

    # ── Conversation sessions ─────────────────────────────────
    def _session(self, key: tuple[int, int]) -> dict:
        now = time.time()
        for stale in [k for k, v in self._chats.items() if now - v["ts"] > SESSION_TTL]:
            del self._chats[stale]
        session = self._chats.get(key)
        if session is None:
            session = self._chats[key] = {"messages": [], "ts": now}
        session["ts"] = now
        return session

    @staticmethod
    def _trim(messages: list[dict]) -> None:
        """Keep the most recent MAX_HISTORY messages and ensure the list still
        starts with a user turn (the API requires it)."""
        if len(messages) > MAX_HISTORY:
            del messages[: len(messages) - MAX_HISTORY]
        if messages and messages[0]["role"] != "user":
            del messages[0]

    # ── Commands ──────────────────────────────────────────────
    @app_commands.command(description="Ask Codex a one-off question.")
    @app_commands.describe(question="What do you want to ask?")
    @app_commands.checks.cooldown(1, 15.0)  # 1 use / 15s per user — caps spam & cost
    async def ask(self, interaction: discord.Interaction, question: str) -> None:
        if not config.ANTHROPIC_API_KEY:
            await interaction.response.send_message(NOT_CONFIGURED, ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        answer, usage = await self._complete(
            system=ASK_SYSTEM,
            messages=[{"role": "user", "content": question}],
        )
        embed = discord.Embed(description=answer[:EMBED_LIMIT], color=config.COLOR)
        embed.set_author(
            name=f"Asked by {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url,
        )
        embed.set_footer(text=f"Codex AI · {config.AI_MODEL} · {_fmt_usage(usage)}")
        await interaction.followup.send(content=f"> {question[:256]}", embed=embed)

    @app_commands.command(description="Chat with Codex — it remembers the conversation (cached).")
    @app_commands.describe(message="Your message to Codex.")
    @app_commands.checks.cooldown(1, 8.0)
    async def chat(self, interaction: discord.Interaction, message: str) -> None:
        if not config.ANTHROPIC_API_KEY:
            await interaction.response.send_message(NOT_CONFIGURED, ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        key = (interaction.channel_id or 0, interaction.user.id)
        session = self._session(key)
        session["messages"].append({"role": "user", "content": message})
        answer, usage = await self._complete(
            system=CHAT_SYSTEM, messages=session["messages"], cache=True
        )
        session["messages"].append({"role": "assistant", "content": answer})
        self._trim(session["messages"])
        embed = discord.Embed(description=answer[:EMBED_LIMIT], color=config.COLOR)
        embed.set_footer(
            text=f"Codex AI · {config.AI_MODEL} · {_fmt_usage(usage)} · /endchat to reset"
        )
        await interaction.followup.send(content=f"> {message[:256]}", embed=embed)

    @app_commands.command(description="Clear your Codex conversation in this channel.")
    async def endchat(self, interaction: discord.Interaction) -> None:
        key = (interaction.channel_id or 0, interaction.user.id)
        cleared = self._chats.pop(key, None) is not None
        await interaction.response.send_message(
            "🧹 Conversation cleared." if cleared else "No active conversation here.",
            ephemeral=True,
        )

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
        answer, usage = await self._complete(
            system=SUMMARY_SYSTEM,
            messages=[{"role": "user", "content": f"Summarise this conversation:\n\n{transcript}"}],
        )
        embed = discord.Embed(
            title=f"📝 Summary of the last {len(history)} messages",
            description=answer[:EMBED_LIMIT],
            color=config.COLOR,
        )
        embed.set_footer(text=f"Codex AI · {config.AI_MODEL} · {_fmt_usage(usage)}")
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
