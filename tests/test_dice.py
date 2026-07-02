"""Unit tests for the gaming cog's dice-notation regex."""

from __future__ import annotations

from cogs.gaming import _DICE_RE


def test_valid_notation() -> None:
    assert _DICE_RE.match("2d6").groups() == ("2", "6", None)
    assert _DICE_RE.match("d20").groups() == ("", "20", None)  # implicit count of 1
    assert _DICE_RE.match("3d8+2").groups() == ("3", "8", "+2")
    assert _DICE_RE.match("1d100-5").groups() == ("1", "100", "-5")


def test_case_insensitive() -> None:
    assert _DICE_RE.match("2D6") is not None


def test_rejects_garbage() -> None:
    for bad in ("d", "2d", "d%", "abc", "2d6d6", "2x6", ""):
        assert _DICE_RE.match(bad) is None, f"should reject {bad!r}"
