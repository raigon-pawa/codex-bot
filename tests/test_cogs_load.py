"""Smoke test: every registered extension must import and load cleanly.

This is the cheapest, highest-value guard for an incrementally built bot — it
catches a broken cog before it ever reaches Discord. CI runs it on every push/PR.
Dummy credentials are provided by ``conftest.py``.
"""

from __future__ import annotations

import bot as botmod


async def test_all_extensions_load() -> None:
    client = botmod.CodexBot()
    try:
        for ext in botmod.INITIAL_EXTENSIONS:
            await client.load_extension(ext)
        assert client.cogs, "no cogs were loaded"
        command_names = {c.name for c in client.tree.get_commands()}
        assert {"ping", "rank", "panel"} <= command_names
    finally:
        await client.close()
