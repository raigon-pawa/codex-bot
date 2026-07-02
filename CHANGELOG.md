# Changelog

All notable changes to Codex are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.1.0] — 2026-07-02

Post-1.0 polish and hardening: per-server settings, a full music control panel
with interactive seeking, real test coverage, several fixes, and container health.

### Added
- **Player control panel** — buttons under the Now Playing message for seek −15s /
  pause-resume / skip / seek +15s / volume down / up. Interactive seeking restarts
  FFmpeg at the new offset (`-ss`) without advancing the queue; controls are
  limited to members in the voice channel and to the newest player message.
- **Live seekbar** — the Now Playing message shows a progress bar that updates as
  the track plays (frame-counted, so no wall-clock drift), freezes on pause, and
  is rendered on demand by `/music nowplaying`.
- `settings` cog — **per-server prefix** (`/prefix show|set|reset`) and a
  **configurable welcome/goodbye channel** (`/welcome set|disable|status`). Adds
  `guild_config.prefix` with a migration for existing databases.
- `owner` cog — an owner-only `!sync` prefix command (`!sync` global, `!sync guild`
  for instant per-server updates, `!sync clear` to drop a server's guild commands).
- **Cancel reminders** — `/reminders` now has a dropdown to remove a pending one.
- **Ladder position in leveling** — `/rank` shows your **#position**; `/leaderboard`
  appends your own rank when you're outside the top 10.
- **Auto-deploy workflow** (`.github/workflows/deploy.yml`) — a self-hosted runner
  on the NAS rebuilds Codex whenever `main` passes CI (outbound-only), plus a
  `workflow_dispatch` "Run workflow" button.
- **Docker healthcheck** — a 30s heartbeat + `healthcheck.py` probe, so `docker ps`
  shows `unhealthy` if the bot wedges or never connects. New optional `HEALTH_FILE`.
- **Expanded test suite** (1 → 21) — duration parsing, the XP curve + rank position,
  dice notation, seekbar formatting, the DB migration, and prefix resolution.

### Changed
- **Commands now sync globally on startup** so every server Codex joins gets them.
  Previously `DEV_GUILD_ID` synced to that one server only (now legacy/unused).
- `/help` is now **paginated** — one category per page with Prev/Next buttons, a
  jump dropdown, and a page counter — and lists the command **groups** and
  **context menus** the old flat list omitted.
- **Info commands are now hybrid** — `ping`, `help`, `serverinfo`, `userinfo`,
  `rank`, and `leaderboard` work as both slash (`/ping`) and prefix (`!ping`).
- **"Report Message" now actually reports** — the context menu posts an embed to
  the mod-log channel from `/logging set` instead of a no-op acknowledgement.

### Fixed
- **Music voice crash** — `/music play` failed with `davey library needed in order
  to use voice`; switched to the `discord.py[voice]` extra (PyNaCl **and** davey).
- **Seekbar stuck near the end** — naturally-ended tracks now finalize with a full
  bar and a "✅ Finished" title; skips/stops don't falsely show as finished.
- **`/premium` crash** — the upgrade prompt used `None` for an absent view (raising
  `NoneType has no attribute 'is_finished'`); now uses discord's `MISSING` sentinel.
- **Default-prefix env collision** — the default prefix reads `BOT_PREFIX` first
  (`PREFIX` is a common system env var); `PREFIX` still honoured for back-compat.

## [1.0.0] — 2026-07-01

The first stable release: every cog on the roadmap shipped — 29 slash commands
and 2 context menus across AI, study, roles, gaming, moderation/AutoMod, music,
and a premium tier.

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
- `music` cog — voice playback with a per-guild queue: `/music play` (URL or
  search via yt-dlp), plus `skip`, `pause`, `resume`, `stop`, `queue`,
  `nowplaying`, `volume`, and `leave`. Streams through FFmpeg with live volume
  control and auto-leaves when idle or left alone.
- `premium` cog — Discord App Subscriptions: `/premium status|perks|exclusive`
  gate perks on a SKU entitlement (native upgrade button included), and
  `/premium skus` (owner-only) lists the app's SKU IDs for setup. New optional
  `PREMIUM_SKU_ID` config; the cog no-ops gracefully until it's set.

### Changed
- Default `AI_MODEL` is now `claude-haiku-4-5` (~5× cheaper than Opus) to minimise
  cost; set `AI_MODEL=claude-opus-4-8` for top quality.
- Docker self-hosting: `Dockerfile`, hardened `docker-compose.yml`, and a
  "Self-hosting with Docker" guide in the README. The image now bundles **FFmpeg**
  for the music cog.
- Added `PyNaCl` (voice encryption) and `yt-dlp` (audio resolution) to
  `requirements.txt`.

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

[Unreleased]: https://github.com/raigon-pawa/codex-bot/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/raigon-pawa/codex-bot/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/raigon-pawa/codex-bot/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/raigon-pawa/codex-bot/releases/tag/v0.1.0
