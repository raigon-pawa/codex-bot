"""Tiny async SQLite layer shared across cogs.

Each cog opens a short-lived connection with `aiosqlite.connect(config.DB_PATH)`.
Call `init_db()` once on startup to create the schema.
"""

from __future__ import annotations

import os

import aiosqlite

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS levels (
    guild_id INTEGER NOT NULL,
    user_id  INTEGER NOT NULL,
    xp       INTEGER NOT NULL DEFAULT 0,
    level    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS guild_config (
    guild_id        INTEGER PRIMARY KEY,
    welcome_channel INTEGER,
    log_channel     INTEGER
);

CREATE TABLE IF NOT EXISTS reminders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    remind_at  REAL    NOT NULL,
    message    TEXT    NOT NULL
);
"""


async def init_db() -> None:
    """Create the database file and tables if they don't exist."""
    folder = os.path.dirname(config.DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
