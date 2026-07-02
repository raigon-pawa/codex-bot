"""Unit tests for the music cog's seekbar formatters."""

from __future__ import annotations

from cogs.music import _clock, _fmt_duration, _progress_bar


def test_clock() -> None:
    assert _clock(0) == "0:00"
    assert _clock(9) == "0:09"
    assert _clock(83) == "1:23"
    assert _clock(3725) == "1:02:05"  # rolls over to H:MM:SS


def test_fmt_duration() -> None:
    assert _fmt_duration(None) == "live"
    assert _fmt_duration(0) == "live"
    assert _fmt_duration(90) == "1:30"


def test_progress_bar_live() -> None:
    assert "LIVE" in _progress_bar(10, None)
    assert "LIVE" in _progress_bar(10, 0)


def test_progress_bar_shows_position_and_total() -> None:
    bar = _progress_bar(30, 120)
    assert "🔘" in bar  # the knob
    assert "0:30" in bar
    assert "2:00" in bar


def test_progress_bar_clamps_overrun() -> None:
    # elapsed past total must not overflow the fixed-width bar or crash
    bar = _progress_bar(999, 100)
    assert "🔘" in bar
    assert "1:40" in bar  # total still renders (100s)
