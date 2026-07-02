# syntax=docker/dockerfile:1

# Codex runtime image. A slim base + prebuilt wheels means a small image with
# no compiler toolchain needed.
FROM python:3.13-slim

# Predictable, log-friendly Python behaviour inside containers.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DB_PATH=/app/data/codex.db

WORKDIR /app

# FFmpeg is the audio backend for the music cog (PyNaCl + yt-dlp come from pip).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first so this layer stays cached when only code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the runtime code (everything else is excluded via .dockerignore).
COPY bot.py config.py healthcheck.py ./
COPY core/ ./core/
COPY cogs/ ./cogs/

# Run as a non-root user that owns the writable data directory.
RUN useradd --create-home --uid 10001 codex \
    && mkdir -p /app/data \
    && chown -R codex:codex /app
USER codex

# Report "unhealthy" if the bot stops writing its heartbeat (wedged / not connected).
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "healthcheck.py"]

CMD ["python", "bot.py"]
