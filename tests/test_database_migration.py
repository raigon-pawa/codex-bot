"""Tests for the SQLite layer: schema creation, idempotency, and the
guild_config.prefix migration for databases that predate that column."""

from __future__ import annotations

import aiosqlite

import config
from core.database import init_db


async def test_fresh_db_has_prefix_column(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "fresh.db")
    monkeypatch.setattr(config, "DB_PATH", db_path)
    await init_db()
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("PRAGMA table_info(guild_config)")
        columns = {row[1] for row in await cursor.fetchall()}
    assert "prefix" in columns


async def test_init_db_is_idempotent(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "twice.db")
    monkeypatch.setattr(config, "DB_PATH", db_path)
    await init_db()
    await init_db()  # must not raise on an already-migrated DB


async def test_migration_adds_prefix_and_keeps_data(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "old.db")
    monkeypatch.setattr(config, "DB_PATH", db_path)
    # An OLD database: guild_config without the prefix column, with a row.
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "CREATE TABLE guild_config ("
            "guild_id INTEGER PRIMARY KEY, welcome_channel INTEGER, log_channel INTEGER)"
        )
        await db.execute("INSERT INTO guild_config (guild_id, log_channel) VALUES (42, 999)")
        await db.commit()

    await init_db()

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("PRAGMA table_info(guild_config)")
        columns = {row[1] for row in await cursor.fetchall()}
        cursor = await db.execute("SELECT log_channel, prefix FROM guild_config WHERE guild_id=42")
        row = await cursor.fetchone()
    assert "prefix" in columns
    assert row == (999, None)  # existing data preserved, new column defaults NULL
