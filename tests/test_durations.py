"""Unit tests for study.parse_duration."""

from __future__ import annotations

from cogs.study import MAX_DURATION, parse_duration


def test_basic_units() -> None:
    assert parse_duration("45s") == 45
    assert parse_duration("10m") == 600
    assert parse_duration("2h") == 7200
    assert parse_duration("1d") == 86400


def test_compound() -> None:
    assert parse_duration("1h30m") == 5400
    assert parse_duration("1d2h") == 86400 + 7200


def test_whitespace_and_case() -> None:
    assert parse_duration("10 M") == 600
    assert parse_duration("1H 30M") == 5400


def test_invalid_returns_none() -> None:
    assert parse_duration("") is None
    assert parse_duration("soon") is None
    assert parse_duration("10x") is None


def test_zero_and_bounds() -> None:
    assert parse_duration("0m") is None  # must be > 0
    assert parse_duration("30d") == MAX_DURATION
    assert parse_duration("31d") is None  # over the 30-day cap
