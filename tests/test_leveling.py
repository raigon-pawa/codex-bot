"""Unit tests for social.xp_for_level."""

from __future__ import annotations

from cogs.social import xp_for_level


def test_known_values() -> None:
    assert xp_for_level(0) == 100  # 5*0 + 50*0 + 100
    assert xp_for_level(1) == 155  # 5*1 + 50 + 100
    assert xp_for_level(10) == 1100  # 5*100 + 500 + 100


def test_strictly_increasing() -> None:
    previous = -1
    for level in range(0, 200):
        needed = xp_for_level(level)
        assert needed > previous, f"xp_for_level not monotonic at {level}"
        previous = needed
