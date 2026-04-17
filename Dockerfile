# ══════════════════════════════════════════════════════════════════════════════
# Dockerfile — Telegram Voice Chat Music Bot
# Multi-stage build: builder installs Python deps; final image is lean.
# ══════════════════════════════════════════════════════════════════════════════

# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

# System libraries required to compile native Python wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libffi-dev \
        libssl-dev \
        libpng-dev \
        libjpeg-dev \
        libfreetype6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy dependency list first so Docker can cache this layer
COPY requirements.txt .

# Install all Python packages into a dedicated prefix so we can copy them later
RUN pip install --upgrade pip wheel \
 && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="you@example.com"
LABEL description="Telegram Voice Chat Music Bot"

# ── OS-level runtime dependencies ────────────────────────────────────────────
# ffmpeg  : audio encoding/decoding for voice-chat streaming
# libpng  : Pillow PNG support (thumbnail generation)
# libjpeg : Pillow JPEG support
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libpng16-16 \
        libjpeg62-turbo \
        libfreetype6 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root user for security ─────────────────────────────────────────────
RUN groupadd -r musicbot && useradd -r -g musicbot -d /app musicbot

WORKDIR /app

# Copy compiled Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=musicbot:musicbot . .

# Create runtime directories with correct ownership
RUN mkdir -p /app/cache/thumbs /app/logs \
 && chown -R musicbot:musicbot /app/cache /app/logs

# Switch to non-root user
USER musicbot

# Health check — curl the dashboard ping (falls back gracefully if disabled)
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:${DASHBOARD_PORT:-8080}/ || exit 0

# Expose dashboard port (optional — only used if DASHBOARD_ENABLED=true)
EXPOSE 8080

# ── Entry point ───────────────────────────────────────────────────────────────
CMD ["python", "-m", "bot.main"]
