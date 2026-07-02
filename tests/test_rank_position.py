"""Tests for social.rank_position — 1-based ladder position from (level, xp)."""

from __future__ import annotations

import aiosqlite

import config
from cogs.social import rank_position
from core.database import init_db


async def _seed(
    db: aiosqlite.Connection, guild_id: int, members: list[tuple[int, int, int]]
) -> None:
    for user_id, level, xp in members:
        await db.execute(
            "INSERT INTO levels (guild_id, user_id, level, xp) VALUES (?,?,?,?)",
            (guild_id, user_id, level, xp),
        )
    await db.commit()


async def test_positions(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "ranks.db")
    monkeypatch.setattr(config, "DB_PATH", db_path)
    await init_db()
    async with aiosqlite.connect(db_path) as db:
        # (user, level, xp): user 1 top, then 2, then 3
        await _seed(db, 100, [(1, 5, 50), (2, 5, 10), (3, 3, 90)])
        assert await rank_position(db, 100, 5, 50) == 1  # highest
        assert await rank_position(db, 100, 5, 10) == 2  # same level, less xp
        assert await rank_position(db, 100, 3, 90) == 3  # lower level
        # a brand-new member below everyone
        assert await rank_position(db, 100, 0, 0) == 4
        # a hypothetical score above everyone
        assert await rank_position(db, 100, 9, 0) == 1
        # different guild is isolated
        assert await rank_position(db, 999, 0, 0) == 1
