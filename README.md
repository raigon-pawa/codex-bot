# Codex

Codex is a modular Discord bot designed for university groups, gaming friends, and casual
communities who want productivity + fun in one place. Built for private friend servers but
powerful enough for public release, Codex combines study tools, AI assistance, gaming
utilities, and social features into a smooth, modern experience.

Built with **[discord.py](https://discordpy.readthedocs.io/) 2.7** on **Python 3.14**.

---

## What's in this repo right now

A complete, runnable foundation that already exercises the main Discord interaction
surfaces, so you can confirm everything works before piling on features:

| Cog            | What it demonstrates                                                        |
|----------------|-----------------------------------------------------------------------------|
| `general`      | Hybrid commands — `/ping` **and** `!ping` (`serverinfo`, `userinfo`, `help`) |
| `events`       | Welcome / goodbye messages to a configurable channel (`members` intent)     |
| `moderation`   | Permission-gated commands (`/kick`, `/ban`, `/timeout`, `/clear`)           |
| `components`   | Buttons, select menus, modals, **and** user/message context menus           |
| `social`       | XP & levels with SQLite persistence (`/rank`, `/leaderboard`)               |
| `ai`           | Claude `/ask`, `/chat` (cached multi-turn memory), `/summarize`              |
| `study`        | `/pomodoro`, `/remindme` (SQLite-backed), `/flashcards` deck                 |
| `roles`        | Button self-assign roles (persistent) + auto level-up roles                  |
| `gaming`       | Native `/poll`, `/roll` dice, `/trivia`, `/lfg` board                        |
| `automod`      | Native AutoMod rule management + an audit **mod-log** (`/automod`, `/logging`)|
| `music`        | Voice playback via yt-dlp + FFmpeg (`/music play`, queue, volume, …)         |
| `premium`      | App Subscriptions — SKU/entitlement-gated perks (`/premium`)                 |
| `owner`        | Owner-only prefix commands — `!sync` (global / guild / clear)                |
| `settings`     | Per-server config — `/prefix` and `/welcome` (channel + on/off)             |

31 slash commands + 2 context menus, all verified to load. Common info commands
(`ping`, `help`, `serverinfo`, `userinfo`, `rank`, `leaderboard`) are **hybrid** —
they work as both `/cmd` and `!cmd`.

---

## Quick start

```bash
# 1. Create & activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure secrets
cp .env.example .env               # then edit .env (see Part 1 below)

# 4. Run
python bot.py
```

> **Python 3.14 note:** discord.py needs the `audioop` module for voice, which was removed
> from the standard library in Python 3.13. The `audioop-lts` package restores it and is
> pulled in automatically as a dependency — no action needed.

> **Music note:** the `music` cog streams audio through **FFmpeg**, which must be installed
> and on your `PATH` (`sudo apt install ffmpeg`, `brew install ffmpeg`, …). The Docker image
> installs it for you. `PyNaCl` and `yt-dlp` come from `requirements.txt`.

---

## Part 1 — Discord Developer Portal setup

Everything below happens at <https://discord.com/developers/applications>.

### 1.1 Create the application

1. Click **New Application**, name it `Codex`, accept the terms, **Create**.
2. On **General Information**, set the description, app icon, and tags. Copy the
   **Application ID** → this is `APPLICATION_ID` in your `.env`.
3. (Optional) Set **Interactions Endpoint URL** only if you ever go HTTP-only. With
   discord.py you connect over the **gateway**, so leave this blank.

### 1.2 The Bot user & token

1. Open the **Bot** tab.
2. Click **Reset Token**, confirm, and copy it → this is `DISCORD_TOKEN` in `.env`.
   Treat it like a password; never commit it. (`.env` is already git-ignored.)
3. Set the bot's **username**, **avatar**, and **banner** here.
4. **Public Bot** — turn OFF while it's a private friends' bot; ON when you want anyone
   to be able to invite it.
5. **Requires OAuth2 Code Grant** — leave OFF unless you have a backend doing the auth-code
   flow.

### 1.3 Privileged Gateway Intents  ← easy to miss

Still on the **Bot** tab, scroll to **Privileged Gateway Intents** and enable all three:

- **Presence Intent** — member online status / activities.
- **Server Members Intent** — join/leave events, member lists, role automation.
- **Message Content Intent** — read message text (needed for the leveling system,
  prefix commands, and AI replies).

These mirror the three privileged intents Codex requests in `config.py`. **If they're
off here, the bot crashes on login** with `PrivilegedIntentsRequired`.

> Once your bot is in 100+ servers you must apply for verification to keep privileged
> intents. For a private friends' server you're fine.

### 1.4 Installation contexts (Guild install vs User install)

Open the **Installation** tab. Discord now supports two install targets:

- **Guild Install** — the classic "add bot to a server." Set **Scopes** to `bot` +
  `applications.commands` and pick default permissions.
- **User Install** — installs the app to a *user*, so its commands work in DMs and in
  servers where the bot isn't a member. Great for personal utility commands.

Pick the **Install Link** type (Discord Provided Link is easiest), and the generated URL
is what you share to add Codex.

### 1.5 OAuth2 — scopes & permissions (manual invite URL)

If you'd rather build the invite link by hand, open **OAuth2 → URL Generator**:

1. **Scopes:** check `bot` and `applications.commands`.
2. A **Bot Permissions** box appears. For Codex's current + planned features, select:
   `View Channels`, `Send Messages`, `Send Messages in Threads`, `Embed Links`,
   `Attach Files`, `Read Message History`, `Add Reactions`, `Use External Emojis`,
   `Manage Messages` (for `/clear`), `Manage Roles` (reaction roles / level roles),
   `Kick Members`, `Ban Members`, `Moderate Members` (timeouts),
   `Manage Events`, `Connect` + `Speak` (voice/music later).
3. Copy the generated URL at the bottom, open it, pick your server, **Authorize**.

> Prefer not to grant `Administrator` — it's a security risk and hides which permissions
> a feature actually needs.

### 1.6 Command syncing (and instant updates while testing)

Codex syncs its slash commands **globally** on startup, so every server it's in gets them.
Global syncs can take **up to ~1 hour** to appear the first time.

While developing, that wait is annoying, so there's an owner-only prefix command:

- `!sync guild` — sync to the current server **instantly** (great for testing).
- `!sync` — force a global re-sync (e.g. after adding a command).
- `!sync clear` — remove the current server's guild-specific commands (clears duplicates
  if you previously used a per-guild sync).

You can also mention the bot: `@Codex sync`. (`DEV_GUILD_ID` in `.env` is legacy and no
longer used — global sync is automatic.)

---

## Part 2 — Run it

1. Fill in `.env`:
   ```ini
   DISCORD_TOKEN=your-bot-token
   APPLICATION_ID=your-app-id
   DEV_GUILD_ID=your-test-server-id   # optional but recommended while developing
   ```
2. `python bot.py`
3. You should see `Synced N commands…` and `Online as Codex#1234`. Type `/` in your server
   and Codex's commands appear.

---

## Part 3 — Mapping every Discord feature to Codex

You asked to use as much of what Discord offers as possible. Here's the full surface and
where each piece lives (✅ built, 🔜 on the roadmap):

| Discord feature                         | Used by / planned module                          | Status |
|-----------------------------------------|---------------------------------------------------|:------:|
| Slash commands                          | every cog                                         | ✅ |
| User & message **context menus**        | `components` (Avatar, Report Message)             | ✅ |
| **Embeds**                              | everywhere                                         | ✅ |
| **Buttons / Select menus / Modals**     | `components`                                       | ✅ |
| **Persistent views** (survive restart)  | `components` (PanelView)                           | ✅ |
| Privileged **intents** (members/content)| `events`, `social`                                | ✅ |
| **Gateway events** (join/leave/message) | `events`, `social`                                | ✅ |
| **Permissions** & default-perms gating  | `moderation`                                       | ✅ |
| **Timeouts** (communication disabled)   | `moderation`                                       | ✅ |
| Persistence (SQLite)                    | `core/database`, `social`                          | ✅ |
| **AI assistance** (Claude)              | `ai` — `/ask`, `/chat`, `/summarize`               | ✅ |
| **Prompt caching** (cost saving)        | `ai` — `/chat` caches conversation history          | ✅ |
| Study tools                             | `study` — pomodoro, reminders, flashcards         | ✅ |
| **Reminders / scheduled tasks**         | `study` (via `discord.ext.tasks` loop)            | ✅ |
| **Polls** (native Discord polls)        | `gaming` — `/poll`                                 | ✅ |
| Gaming utilities                        | `gaming` — dice, trivia, LFG                        | ✅ |
| **Reaction roles** / self-assign roles  | `roles` — button panel + auto level roles          | ✅ |
| **AutoMod** rule management             | `automod` — `/automod` keyword/preset/mention rules| ✅ |
| **Audit log** streaming                 | `automod` — `/logging` → mod-log channel           | ✅ |
| **Voice / music**                       | `music` — `/music play` (yt-dlp + FFmpeg)          | ✅ |
| **App Subscriptions / Entitlements**    | `premium` — SKU/entitlement-gated perks             | ✅ |
| **Scheduled Events** (study sessions)   | `events` extension                                 | 🔜 |
| **Webhooks** (announcements/feeds)      | `webhooks`                                          | 🔜 |
| **Application Emojis**                  | branding / reactions                               | 🔜 |
| **Linked Roles** (role-connection meta) | `linkedroles` (e.g. "verified student")           | 🔜 |
| **Soundboard / Stage channels**         | community/events features                           | 🔜 |

### Enabling Premium (App Subscriptions)

The `premium` cog gates perks on a Discord **subscription SKU** — Discord handles
the payment, so there's no billing code on our side. To turn it on:

1. **Developer Portal → Monetization** — complete the eligibility steps and create
   a **subscription SKU**. (Monetization has requirements; the cog runs fine
   unconfigured until you're approved.)
2. Run **`/premium skus`** (owner-only — set `OWNER_IDS` first) to read the SKU's ID.
3. Put it in **`PREMIUM_SKU_ID`** (`.env`) and restart. `/premium status` and the
   native upgrade button now reflect real subscriptions.

Gate any command elsewhere with the same one-line entitlement check the cog uses.

---

## Project structure

```
codex-bot/
├── bot.py              # entry point: CodexBot, extension loading, command sync
├── config.py           # env loading, intents, brand colour
├── requirements.txt
├── .env.example        # copy to .env
├── core/
│   └── database.py     # async SQLite helper + schema
└── cogs/               # one module per feature area
    ├── general.py
    ├── events.py
    ├── moderation.py
    ├── components.py
    ├── social.py
    ├── ai.py           # Claude /ask, /chat (cached), /summarize
    ├── study.py        # pomodoro, reminders, flashcards
    ├── roles.py        # self-assign + level roles
    ├── gaming.py       # polls, dice, trivia, LFG
    ├── automod.py      # AutoMod rules + mod-log
    ├── music.py        # voice playback (yt-dlp + FFmpeg)
    ├── premium.py      # App Subscriptions (SKUs + entitlements)
    ├── owner.py        # owner-only !sync command
    └── settings.py     # per-server prefix (/prefix)
```

**Adding a feature** = drop a new file in `cogs/`, write a `Cog` subclass with an
`async def setup(bot)` at the bottom, and add its dotted path to `INITIAL_EXTENSIONS`
in `bot.py`. That's the whole pattern.

---

## Self-hosting with Docker

Codex is built to run on a small always-on machine (a mini PC, NAS, or Raspberry Pi),
containerized and hardened out of the box.

### Why your home IP stays private

Codex is a **gateway bot** — it only makes *outbound* connections to Discord and never
listens on a port. So:

- You do **not** port-forward anything on your router.
- Nothing on your machine is reachable from the internet or from Discord users; they
  interact through Discord's servers, never with your box directly.
- The compose file publishes **no ports** on purpose, so nothing is exposed even on your LAN.

The only services that see your machine's IP are the ones Codex connects *out* to (Discord,
and the Anthropic API once the AI cog exists) — ordinary outbound traffic, like a browser.
If you want even that hidden, route the container's egress through a VPN.

### Prerequisites

Install Docker Engine + the Compose plugin, then let your user reach the daemon:

```bash
sudo usermod -aG docker $USER   # then log out and back in
```

> ⚠️ The `docker` group effectively grants root on the host. If you'd rather not grant that,
> prefix the commands below with `sudo`, or set up
> [rootless Docker](https://docs.docker.com/engine/security/rootless/).

### Run it

```bash
cp .env.example .env     # fill in DISCORD_TOKEN, APPLICATION_ID, etc.
chmod 600 .env           # lock the token down to your user

docker compose up -d --build
docker compose logs -f   # watch it come online
```

### Update to the latest version

```bash
git pull
docker compose up -d --build
```

### Auto-deploy on push (self-hosted runner)

`.github/workflows/deploy.yml` rebuilds Codex on the NAS automatically whenever
`main` passes CI. It runs on a **self-hosted GitHub Actions runner** installed on
the NAS: the runner dials *out* to GitHub and waits for jobs, so — like the bot
itself — **nothing is exposed to the internet and you port-forward nothing.**

**1. Install the runner on the NAS.** In the repo: **Settings → Actions → Runners
→ New self-hosted runner → Linux**. Follow the download steps it shows, then
configure it with the `nas` label the workflow targets:

```bash
./config.sh --url https://github.com/raigon-pawa/codex-bot \
            --token <TOKEN_FROM_THE_PAGE> --labels nas
```

**2. Run it as a service** (survives reboots, starts on boot). Install it under
the **same user that owns `~/codex-bot`** and is in the `docker` group:

```bash
sudo ./svc.sh install <your-user>
sudo ./svc.sh start
```

**3. (Optional) point it at your clone.** The workflow deploys in `~/codex-bot`
of the runner's user. If your clone lives elsewhere, set a repository variable
**`DEPLOY_PATH`** (Settings → Secrets and variables → Actions → Variables).

That's it. Merge a PR → CI runs → on success the runner does
`git reset --hard origin/main && docker compose up -d --build` on the NAS.

**Redeploy on demand:** the workflow also has a **Run workflow** button —
**Actions → Deploy to NAS → Run workflow** — to rebuild current `main` without
pushing a commit (handy after editing `.env` on the NAS).

> ⚠️ **Public-repo note.** GitHub advises care with self-hosted runners on public
> repos, because fork PRs can run code on your runner. This setup avoids that: CI
> runs on GitHub-hosted runners, and the deploy triggers **only** after CI succeeds
> on `main` (a push that requires write access) — fork-PR CI runs are filtered out
> and never reach the NAS. For extra safety set **Settings → Actions → General →
> Fork pull request workflows → Require approval for all external contributors**.

### Hardening baked into the container

- Runs as a **non-root** user; all Linux capabilities dropped; `no-new-privileges`.
- **Read-only** root filesystem (only the data volume and `/tmp` are writable).
- **No published ports** — outbound-only, as above.
- **Resource limits** (512 MB RAM, 0.5 CPU) so a bug can't take down the host.
- **Log rotation** so logs never fill the disk.
- The token lives only in `.env` on the host — never in git or the image.

Your XP/levels database persists in the `codex-data` Docker volume across restarts and
updates.

---

## Roadmap (suggested build order)

1. ✅ **`ai`** — `/ask` and `/summarize` powered by Claude (headline feature).
2. ✅ **`study`** — pomodoro timers, `/remindme`, flashcard decks, study-session events.
3. ✅ **`roles`** — reaction/button self-assign roles + automatic level roles.
4. ✅ **`gaming`** — native polls, dice, trivia, and an LFG "looking for group" board.
5. ✅ **`automod` / `logging`** — AutoMod rules and an audit-log mod channel.
6. ✅ **`music`** — voice playback (FFmpeg + yt-dlp).
7. ✅ **`premium`** — App Subscriptions for a public-release tier.

Every roadmap cog is built. Each is an isolated cog, so you can build and test
them one at a time.
