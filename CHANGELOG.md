# Changelog

All notable changes to Codex are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

_Nothing yet._

## [0.1.0] — 2026-07-01

The first runnable foundation.

### Added
- Project scaffolding: `bot.py` entry point, `config.py`, and a modular `cogs/` layout.
- `general` cog — `/ping`, `/serverinfo`, `/userinfo`, `/help` with rich embeds.
- `events` cog — welcome / goodbye messages (members intent).
- `moderation` cog — `/kick`, `/ban`, `/timeout`, `/clear`, gated by Discord permissions.
- `components` cog — buttons, select menus, modals, a persistent panel view, and
  user/message context menus.
- `social` cog — chat XP, levels, `/rank`, and `/leaderboard` backed by SQLite.
- Async SQLite layer (`core/database.py`).
- Developer Portal setup guide and feature map in the README.
- CI pipeline (ruff lint + format, cog-load smoke test) and contributor docs.

[Unreleased]: https://github.com/raigon-pawa/codex-bot/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/raigon-pawa/codex-bot/releases/tag/v0.1.0
