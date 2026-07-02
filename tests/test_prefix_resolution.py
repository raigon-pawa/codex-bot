"""Test that CodexBot.get_prefix resolves the prefix per guild via the
settings cache, falling back to the default for unset guilds and DMs."""

from __future__ import annotations

import types

import bot as botmod
import config


class _FakeGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class _FakeMessage:
    def __init__(self, guild: _FakeGuild | None) -> None:
        self.guild = guild


async def test_get_prefix_per_guild() -> None:
    bot = botmod.CodexBot()
    try:
        await bot.load_extension("cogs.settings")
        # `when_mentioned` needs bot.user.id; stub it (not logged in during tests).
        bot._connection.user = types.SimpleNamespace(id=999)  # type: ignore[attr-defined]
        settings = bot.get_cog("Settings")
        settings.prefixes[222] = "c!"  # type: ignore[attr-defined]

        default_guild = await bot.get_prefix(_FakeMessage(_FakeGuild(111)))  # type: ignore[arg-type]
        custom_guild = await bot.get_prefix(_FakeMessage(_FakeGuild(222)))  # type: ignore[arg-type]
        dm = await bot.get_prefix(_FakeMessage(None))  # type: ignore[arg-type]

        # get_prefix returns [mention, mention_nick, literal_prefix]
        assert default_guild[-1] == config.PREFIX
        assert custom_guild[-1] == "c!"
        assert dm[-1] == config.PREFIX
    finally:
        await bot.close()
