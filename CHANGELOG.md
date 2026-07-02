# Changelog

All notable changes to Codex are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Ladder position in leveling** — `/rank` now shows your **#position** on the
  server, and `/leaderboard` appends your own rank when you're outside the top 10.
- **Cancel reminders** — `/reminders` now shows a dropdown to cancel a pending
  reminder (previously you could list them but never remove one).
- **Configurable welcome/goodbye channel** — `/welcome set|disable|status`
  (Manage Server). Join/leave messages post to the chosen channel, fall back to
  the System Channel by default, and can be turned off. This finally uses the
  `guild_config.welcome_channel` column that had been defined but unused.
- **Expanded test suite** — beyond the load smoke test, added unit tests for
  duration parsing, the XP curve, dice notation, seekbar formatting, the
  `guild_config.prefix` migration, and per-guild prefix resolution (1 → 20 tests).
- **Live seekbar** in the music player — the Now Playing message shows a progress
  bar (`0:42 ▬▬▬🔘▬▬▬ 3:15`) that updates as the track plays, freezes on pause,
  and is also rendered on demand by `/music nowplaying`. Position is tracked by
  counting audio frames, so it stays accurate without wall-clock drift.
- **Player control panel** — buttons under the Now Playing message for seek −15s /
  pause-resume / skip / seek +15s / volume down / up. Interactive seeking restarts
  FFmpeg at the new offset (`-ss`) without advancing the queue. Controls are limited
  to members in the voice channel and to the newest player message.
- Auto-deploy workflow (`.github/workflows/deploy.yml`): a self-hosted runner on
  the NAS rebuilds Codex whenever `main` passes CI — outbound-only, no ports
  exposed. Setup notes in the README. Also exposes a `workflow_dispatch`
  "Run workflow" button to redeploy current `main` on demand.

### Changed
- **"Report Message" now actually reports** — the right-click context menu posts
  an embed (reporter, author, channel, jump link) to the mod-log channel set with
  `/logging set`, instead of the previous no-op acknowledgement. Falls back to a
  helpful note when no mod-log is configured.
- **Info commands are now hybrid** — `ping`, `help`, `serverinfo`, `userinfo`,
  `rank`, and `leaderboard` work as **both** slash (`/ping`) and prefix (`!ping`)
  commands, so the common ones don't need the slash UI. The paginated `/help`
  view is now locked to the invoker (it can post publicly as `!help`).
- **Commands now sync globally on startup** so every server Codex joins gets them.
  Previously, setting `DEV_GUILD_ID` synced to that one server only, so new servers
  showed no commands. `DEV_GUILD_ID` is now legacy/unused.
- `/help` is now **paginated** — one category per page with Prev/Next buttons and
  a jump dropdown (and a page counter). It lists command **groups** (e.g. `/music`,
  `/automod`, `/premium`) and **context menus**, which the old flat list omitted.

### Added
- `owner` cog — an owner-only `!sync` prefix command (`!sync` global, `!sync guild`
  for instant per-server updates, `!sync clear` to drop a server's guild commands).
  A prefix command works even before slash commands have synced to a server.
- `settings` cog — **per-server prefix**: `/prefix show`, `/prefix set` (Manage
  Server), and `/prefix reset`. The bot resolves each server's prefix from an
  in-memory cache (no per-message DB hit); mentioning the bot always works too.
  Adds a `guild_config.prefix` column with a migration for existing databases.

### Fixed
- **Default-prefix env collision** — the default prefix now reads `BOT_PREFIX`
  first (`PREFIX` is a common *system* env var that could silently override it).
  `PREFIX` is still honoured for backward compatibility.
- **Music voice crash** — `/music play` failed with `davey library needed in
  order to use voice`. discord.py 2.7's voice stack needs both PyNaCl **and**
  `davey`; switched to the `discord.py[voice]` extra so both are installed.
- **`/premium` crash** — `/premium exclusive` (and `status`) raised
  `NoneType has no attribute 'is_finished'` when `PREMIUM_SKU_ID` was unset;
  the upgrade prompt now uses discord's `MISSING` sentinel instead of `None`
  for the (absent) view.
- **Seekbar stuck near the end** — a finished track left the bar a few seconds
  short (the last live tick is up to 12s stale and yt-dlp's duration often runs
  past the real audio). Naturally-ended tracks now finalize with a full bar and
  a "✅ Finished" title; skips/stops don't falsely show as finished.

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

[Unreleased]: https://github.com/raigon-pawa/codex-bot/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/raigon-pawa/codex-bot/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/raigon-pawa/codex-bot/releases/tag/v0.1.0
