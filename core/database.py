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
    log_channel     INTEGER,
    prefix          TEXT
);

CREATE TABLE IF NOT EXISTS reminders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    remind_at  REAL    NOT NULL,
    message    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS flashcards (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id   INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    front      TEXT    NOT NULL,
    back       TEXT    NOT NULL,
    created_at REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS self_roles (
    guild_id INTEGER NOT NULL,
    role_id  INTEGER NOT NULL,
    emoji    TEXT,
    PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS level_roles (
    guild_id INTEGER NOT NULL,
    level    INTEGER NOT NULL,
    role_id  INTEGER NOT NULL,
    PRIMARY KEY (guild_id, level)
);
"""


async def init_db() -> None:
    """Create the database file and tables if they don't exist."""
    folder = os.path.dirname(config.DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.executescript(SCHEMA)
        await _apply_migrations(db)
        await db.commit()


async def _apply_migrations(db: aiosqlite.Connection) -> None:
    """Add columns to databases created before those columns existed.

    `CREATE TABLE IF NOT EXISTS` never alters an existing table, so new columns
    on old tables need an explicit ALTER guarded by a column check.
    """
    cursor = await db.execute("PRAGMA table_info(guild_config)")
    columns = {row[1] for row in await cursor.fetchall()}
    if "prefix" not in columns:
        await db.execute("ALTER TABLE guild_config ADD COLUMN prefix TEXT")
