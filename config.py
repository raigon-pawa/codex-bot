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
# Legacy: commands now sync globally on startup; use `!sync guild` for instant
# per-server updates. Kept for backward compatibility (no longer used at startup).
DEV_GUILD_ID: int | None = _optional_int("DEV_GUILD_ID")
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
# Claude model for the AI cog. Default is the cost-effective Haiku tier; set
# AI_MODEL=claude-opus-4-8 (best quality) or claude-sonnet-4-6 (mid) to upgrade.
AI_MODEL: str = os.getenv("AI_MODEL", "claude-haiku-4-5")
AI_MAX_TOKENS: int = int(os.getenv("AI_MAX_TOKENS", "1024"))
PREFIX: str = os.getenv("PREFIX", "!")
OWNER_IDS: set[int] = {int(x) for x in os.getenv("OWNER_IDS", "").split(",") if x.strip()}
DB_PATH: str = os.getenv("DB_PATH", "data/codex.db")
# SKU that represents the paid tier (Developer Portal → Monetization). When set,
# the premium cog gates its perks on an entitlement for this SKU. Find the ID
# with `/premium skus` after creating the SKU.
PREMIUM_SKU_ID: int | None = _optional_int("PREMIUM_SKU_ID")

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
