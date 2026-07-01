"""Codex — a modular Discord bot. Entry point.

Run with:  python bot.py
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

import config

log = logging.getLogger("codex")

# Feature modules ("cogs") loaded on startup. Add new ones here.
INITIAL_EXTENSIONS = (
    "cogs.general",
    "cogs.events",
    "cogs.moderation",
    "cogs.components",
    "cogs.social",
    "cogs.ai",
    "cogs.study",
    "cogs.roles",
    "cogs.gaming",
    "cogs.automod",
    "cogs.music",
    "cogs.premium",
)


class CodexBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned_or(config.PREFIX),
            intents=config.INTENTS,
            application_id=config.APPLICATION_ID,
            help_command=None,
            owner_ids=config.OWNER_IDS or None,
            # Never let the bot ping @everyone/@here or roles by accident.
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False),
            activity=discord.Activity(type=discord.ActivityType.listening, name="/help"),
        )

    async def setup_hook(self) -> None:
        """Runs once after login, before connecting to the gateway."""
        for ext in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(ext)
                log.info("Loaded extension: %s", ext)
            except Exception:
                log.exception("Failed to load extension: %s", ext)

        # Sync application (slash) commands with Discord.
        if config.DEV_GUILD_ID:
            # Dev mode: copy global commands to one guild for INSTANT updates.
            guild = discord.Object(id=config.DEV_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %d commands to dev guild %s", len(synced), config.DEV_GUILD_ID)
        else:
            synced = await self.tree.sync()
            log.info("Synced %d global commands (may take up to ~1h to appear)", len(synced))

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info(
            "Online as %s (ID: %s) — in %d guild(s)",
            self.user,
            self.user.id,
            len(self.guilds),
        )

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        log.error("Text command error in %s: %s", ctx.command, error)


async def main() -> None:
    discord.utils.setup_logging(level=logging.INFO)
    async with CodexBot() as bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down Codex.")
