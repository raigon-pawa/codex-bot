#!/usr/bin/env python3
"""Docker HEALTHCHECK probe.

Passes (exit 0) if the bot wrote a heartbeat recently — see `CodexBot.heartbeat`,
which touches `HEALTH_FILE` every 30s while connected. A stale or missing file
(exit 1) means the event loop is wedged or the bot never came up.
"""

from __future__ import annotations

import os
import sys
import time

HEALTH_FILE = os.getenv("HEALTH_FILE", "/tmp/codex_healthy")
MAX_AGE = 90  # seconds; 3x the 30s heartbeat interval

try:
    age = time.time() - os.path.getmtime(HEALTH_FILE)
except OSError:
    sys.exit(1)  # no heartbeat yet / file missing
sys.exit(0 if age < MAX_AGE else 1)
