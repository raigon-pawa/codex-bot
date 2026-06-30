"""Shared test setup.

pytest imports this before any test module, so we set dummy credentials here.
That lets `config` import without exiting — the tests never connect to Discord.
"""

import os

os.environ.setdefault("DISCORD_TOKEN", "test.token.value")
os.environ.setdefault("APPLICATION_ID", "123456789012345678")
os.environ.setdefault("DB_PATH", "data/test.db")
