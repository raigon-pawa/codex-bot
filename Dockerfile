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

# Install dependencies first so this layer stays cached when only code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# When you add the music cog later, uncomment to install voice support:
#   RUN apt-get update \
#     && apt-get install -y --no-install-recommends ffmpeg \
#     && rm -rf /var/lib/apt/lists/*
#   (and add PyNaCl to requirements.txt)

# Copy only the runtime code (everything else is excluded via .dockerignore).
COPY bot.py config.py ./
COPY core/ ./core/
COPY cogs/ ./cogs/

# Run as a non-root user that owns the writable data directory.
RUN useradd --create-home --uid 10001 codex \
    && mkdir -p /app/data \
    && chown -R codex:codex /app
USER codex

CMD ["python", "bot.py"]
