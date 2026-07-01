"""Owner-only bot administration.

These are **prefix** commands (e.g. `!sync` or `@Codex sync`) on purpose: they
work the moment the bot is in a server, without needing slash commands synced
first — which is exactly the situation you're in when commands aren't showing up.

`!sync` pushes the command tree to Discord:
  - `!sync`        → global — every server (can take up to ~1h the first time)
  - `!sync guild`  → just this server, instantly (handy while testing)
  - `!sync clear`  → remove this server's guild-specific commands (clears any
                     leftover duplicates from an earlier per-guild sync)

Owner = the app owner (or anyone in `OWNER_IDS`); `is_owner` falls back to the
application owner, so no config is required for this to work for you.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

log = logging.getLogger("codex")


class Owner(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.command(name="sync", help="Sync slash commands (global | guild | clear).")
    async def sync(self, ctx: commands.Context, scope: str = "global") -> None:
        scope = scope.lower()
        try:
            if scope in ("guild", "here") and ctx.guild is not None:
                self.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await self.bot.tree.sync(guild=ctx.guild)
                await ctx.reply(
                    f"✅ Synced **{len(synced)}** commands to this server — they show up instantly."
                )
            elif scope == "clear" and ctx.guild is not None:
                self.bot.tree.clear_commands(guild=ctx.guild)
                await self.bot.tree.sync(guild=ctx.guild)
                await ctx.reply("🧹 Cleared this server's guild-specific commands.")
            else:
                synced = await self.bot.tree.sync()
                await ctx.reply(
                    f"✅ Synced **{len(synced)}** global commands. A new server can take up "
                    "to ~1h to show them the first time."
                )
        except discord.HTTPException as exc:
            await ctx.reply(f"Sync failed: {exc.text or exc}")

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CheckFailure):
            return  # not the owner — stay silent
        log.error("Owner command error in %s: %s", ctx.command, error)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Owner(bot))
