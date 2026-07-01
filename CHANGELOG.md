# Changelog

All notable changes to Codex are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `ai` cog — Claude-powered `/ask`, `/chat`, `/summarize`, built on the async
  Anthropic client with per-user cooldowns.
- `/chat` — multi-turn conversation with memory and **prompt caching** on the
  growing history (re-read at ~0.1× input cost once it passes the model minimum);
  `/endchat` clears a conversation. Per-reply token usage shown in the footer.

- `study` cog — `/pomodoro start|stop` focus timers, `/remindme` + `/reminders`
  (SQLite-backed, dispatched by a background task loop so they survive restarts),
  and a per-server `/flashcards add|review|list|delete` deck.
- `roles` cog — `/selfrole add|remove|panel` button self-assign roles (persistent
  via a `DynamicItem`, so panels survive restarts) and `/levelrole set|remove|list`
  that auto-grants roles at XP milestones (driven by a new `level_up` event from
  the `social` cog).
- `gaming` cog — native `/poll`, a `/roll` dice roller (NdM±K notation), `/trivia`
  (Open Trivia DB, multiple-choice answer buttons), and an `/lfg` board with
  Join/Leave buttons.
- `automod` cog — manage Discord's native AutoMod from chat (`/automod
  keyword|preset|mentions|list|remove`) and stream moderation events (message
  edits/deletes, joins/leaves, bans, and AutoMod hits) to a mod-log channel via
  `/logging set|disable|status`. AutoMod alerts route to the same channel.

### Changed
- Default `AI_MODEL` is now `claude-haiku-4-5` (~5× cheaper than Opus) to minimise
  cost; set `AI_MODEL=claude-opus-4-8` for top quality.
- Docker self-hosting: `Dockerfile`, hardened `docker-compose.yml`, and a
  "Self-hosting with Docker" guide in the README.

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
