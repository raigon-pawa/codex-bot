"""Per-server settings — currently the command prefix.

The prefix lives in `guild_config.prefix` and is cached in memory here; the bot's
`get_prefix` reads this cache, so resolving a message's prefix never hits the DB.
Most commands are slash commands and the few text ones are owner-only, but a
custom prefix (and mentioning the bot) still work for those.
"""

from __future__ import annotations

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

import config
from core.database import init_db

_MAX_PREFIX_LEN = 5


class Settings(commands.Cog):
    prefix = app_commands.Group(
        name="prefix",
        description="View or change this server's command prefix.",
        guild_only=True,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.prefixes: dict[int, str] = {}  # guild_id → prefix (read by bot.get_prefix)

    async def cog_load(self) -> None:
        await init_db()
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT guild_id, prefix FROM guild_config WHERE prefix IS NOT NULL"
            )
            rows = await cursor.fetchall()
        self.prefixes = {guild_id: prefix for guild_id, prefix in rows}

    @prefix.command(name="show", description="Show this server's command prefix.")
    async def prefix_show(self, interaction: discord.Interaction) -> None:
        current = self.prefixes.get(interaction.guild_id, config.PREFIX)  # type: ignore[arg-type]
        mention = self.bot.user.mention if self.bot.user else "@Codex"
        embed = discord.Embed(title="Server prefix", color=config.COLOR)
        embed.description = (
            f"This server's prefix is **`{current}`** (e.g. `{current}sync`).\n"
            f"You can also mention me — {mention} `sync` — which always works.\n"
            "Most features are **slash commands**: type `/` to see them."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @prefix.command(name="set", description="Set this server's command prefix.")
    @app_commands.describe(new_prefix="1-5 characters, no spaces (e.g. ! ? c!)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def prefix_set(self, interaction: discord.Interaction, new_prefix: str) -> None:
        cleaned = new_prefix.strip()
        if not cleaned or len(cleaned) > _MAX_PREFIX_LEN or any(ch.isspace() for ch in cleaned):
            await interaction.response.send_message(
                f"Prefix must be 1-{_MAX_PREFIX_LEN} characters with no spaces.", ephemeral=True
            )
            return
        async with aiosqlite.connect(config.DB_PATH) as db:
            await db.execute(
                "INSERT INTO guild_config (guild_id, prefix) VALUES (?,?) "
                "ON CONFLICT(guild_id) DO UPDATE SET prefix=excluded.prefix",
                (interaction.guild_id, cleaned),
            )
            await db.commit()
        self.prefixes[interaction.guild_id] = cleaned  # type: ignore[index]
        await interaction.response.send_message(
            f"✅ Prefix set to **`{cleaned}`**. Mentioning me still works too.", ephemeral=True
        )

    @prefix.command(name="reset", description="Reset the prefix to the default.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def prefix_reset(self, interaction: discord.Interaction) -> None:
        async with aiosqlite.connect(config.DB_PATH) as db:
            await db.execute(
                "UPDATE guild_config SET prefix=NULL WHERE guild_id=?", (interaction.guild_id,)
            )
            await db.commit()
        self.prefixes.pop(interaction.guild_id, None)  # type: ignore[arg-type]
        await interaction.response.send_message(
            f"↩️ Prefix reset to the default **`{config.PREFIX}`**.", ephemeral=True
        )

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        msg = (
            "You need the **Manage Server** permission for that."
            if isinstance(error, app_commands.MissingPermissions)
            else f"Something went wrong: {error}"
        )
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Settings(bot))
