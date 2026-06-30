# Contributing to Codex

Thanks for your interest! Codex is built to be **incremental and modular** — every feature
is a self-contained cog in [`cogs/`](cogs/), so you can add things one at a time without
touching the rest of the bot. This guide explains the workflow.

## 1. Development setup

```bash
git clone https://github.com/raigon-pawa/codex-bot
cd codex-bot

python3 -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate

pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                       # then fill in your test bot's token
```

See the [README](README.md#part-1--discord-developer-portal-setup) for how to create a bot
and get a token. Use a **separate test application** for development — never your
production token.

## 2. Branching model

`main` is always runnable and always green in CI. You never commit directly to it.

```
main
 └─ feat/ai-cog          ← one branch per feature/fix
     └─ (PR) ──────────► merge back into main when CI passes
```

1. Branch off the latest `main`:
   ```bash
   git switch main && git pull
   git switch -c feat/ai-cog
   ```
2. Build the feature (ideally one cog per branch — it keeps PRs small and reviewable).
3. Push and open a Pull Request. CI lints and loads every cog automatically.
4. Squash-merge once it's green. Delete the branch.

**Branch naming:** `feat/…`, `fix/…`, `docs/…`, `refactor/…`, `chore/…`.

## 3. Commit messages — [Conventional Commits](https://www.conventionalcommits.org/)

```
<type>(optional scope): <short summary>

[optional body explaining what & why]
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`.

```
feat(ai): add /ask command backed by Claude
fix(social): stop XP being granted in DMs
docs(readme): document privileged intents step
```

This keeps history readable and makes it easy to auto-generate release notes later.

## 4. Adding a feature — the cog workflow

1. Copy the simplest existing cog, [`cogs/general.py`](cogs/general.py), as a template.
2. Write your `commands.Cog` subclass with an `async def setup(bot)` at the bottom.
3. Register it by adding its dotted path to `INITIAL_EXTENSIONS` in [`bot.py`](bot.py).
4. If it stores data, add a table to [`core/database.py`](core/database.py).
5. Document its commands in the README feature table.

## 5. Before you open a PR

Run the same checks CI will run:

```bash
ruff check . && ruff format .     # lint + auto-format
pytest -q                         # all cogs must still load
```

Then add a line under `[Unreleased]` in [`CHANGELOG.md`](CHANGELOG.md).

## 6. Releases & versioning

Codex follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

- **PATCH** — bug fixes (`0.1.0 → 0.1.1`)
- **MINOR** — a new cog/feature, backwards compatible (`0.1.0 → 0.2.0`)
- **MAJOR** — breaking changes to config/data/commands (`0.x → 1.0.0`)

To cut a release: move `[Unreleased]` notes into a new version section in the changelog,
then tag it:

```bash
git tag -a v0.2.0 -m "Add AI assistance cog"
git push origin v0.2.0
```

Create a GitHub Release from the tag and paste the changelog section as the notes.

## Code of Conduct

By participating you agree to uphold our [Code of Conduct](CODE_OF_CONDUCT.md).
