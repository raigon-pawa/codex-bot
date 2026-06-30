# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Instead, report them privately
via GitHub's [Report a vulnerability](https://github.com/raigon-pawa/codex-bot/security/advisories/new)
form (Security tab → Advisories). You'll get a response as soon as possible.

## Secrets & tokens

Codex reads its bot token and API keys from a local `.env` file, which is **git-ignored**.

- Never commit `.env`, a bot token, or an API key. If one is ever pushed, **reset it
  immediately** in the Discord Developer Portal (Bot → Reset Token) — rotating is the only
  safe fix, because the value is permanently in git history.
- Use a **separate test application** for development, distinct from any production bot.
- Grant the bot only the permissions a feature needs; avoid the `Administrator` permission.

## Privileged intents

Codex requests the Message Content, Server Members, and Presence intents. These expose
user data — handle and store it responsibly, and don't log message contents in production.
