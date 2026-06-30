"""Central configuration for Codex. Values come from the environment / .env file."""

from __future__ import annotations

import os
import sys

import discord
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        sys.exit(
            f"[config] Missing required environment variable: {key}\n"
            f"         Copy .env.example to .env and fill it in."
        )
    return value


def _optional_int(key: str) -> int | None:
    value = os.getenv(key)
    return int(value) if value and value.strip() else None


# ── Required ──────────────────────────────────────────────
DISCORD_TOKEN: str = _require("DISCORD_TOKEN")
APPLICATION_ID: int = int(_require("APPLICATION_ID"))

# ── Optional ──────────────────────────────────────────────
DEV_GUILD_ID: int | None = _optional_int("DEV_GUILD_ID")
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
PREFIX: str = os.getenv("PREFIX", "!")
OWNER_IDS: set[int] = {int(x) for x in os.getenv("OWNER_IDS", "").split(",") if x.strip()}
DB_PATH: str = os.getenv("DB_PATH", "data/codex.db")

# Brand colour for embeds (Discord blurple).
COLOR = discord.Color.from_str("#5865F2")

# ── Intents ───────────────────────────────────────────────
# IMPORTANT: the three privileged intents below must ALSO be toggled on
# in the Developer Portal (Bot → Privileged Gateway Intents). If they are
# off there, the bot will fail to log in with a PrivilegedIntentsRequired
# error.
INTENTS = discord.Intents.default()
INTENTS.message_content = True  # read message text (prefix cmds, AI replies, leveling)
INTENTS.members = True  # join/leave events, member lookups, role management
INTENTS.presences = True  # online status / activity features
