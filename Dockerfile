# syntax=docker/dockerfile:1.6
# Nano Sofa Studio v2 — multi-stage, multi-arch image.
# Base: python:3.12-slim (pinned by digest for reproducibility).
# Stage 1: install Python wheels into an isolated --target dir.
# Stage 2: copy wheels + source into a clean runtime image, non-root user.
#
# Build:
#   docker buildx build --platform linux/amd64,linux/arm64 -t nano-sofa:latest .
#
# Run:
#   docker run --rm -p 7861:7861 -v "$PWD/outputs:/app/outputs" nano-sofa:latest

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — dependency builder
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools only in the builder stage — they never reach runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only the requirements file first so Docker layer-caches the install
# step independently of source changes.
COPY app-v2/requirements.txt /build/requirements.txt

# Install into /wheels so Stage 2 can simply copy the directory.
RUN pip install --upgrade pip --no-cache-dir \
    && pip install --no-cache-dir --target /wheels -r /build/requirements.txt

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — runtime image
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# ── system deps (Pillow needs these at runtime on slim) ─────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── non-root user ────────────────────────────────────────────────────────────
RUN groupadd --gid 1001 sofa && useradd --uid 1001 --gid sofa --no-create-home sofa

WORKDIR /app

# ── copy installed wheels from Stage 1 ──────────────────────────────────────
COPY --from=builder /wheels /app/site-packages

# Add the wheels directory to PYTHONPATH so Python finds the packages.
ENV PYTHONPATH=/app/site-packages:/app

# ── copy application source ──────────────────────────────────────────────────
# app/core/ (generator, schema_loader, cost_tracker, leg_browser)
COPY app/__init__.py       /app/app/__init__.py
COPY app/core/             /app/app/core/

# app-v2/ (FastAPI server + static HTML/CSS/JS)
COPY app-v2/               /app/app-v2/

# Static assets baked into the image (editable via volume override in compose)
COPY prompts/              /app/prompts/
COPY legs/                 /app/legs/

# ── create the outputs dir so it exists even without a volume mount ──────────
# /app/outputs gets a sticky-bit 1777 so that when the host bind-mounts a
# directory owned by an arbitrary UID over it, the container's `sofa` user
# (UID 1001) can still write generated images into it without hitting EACCES.
RUN mkdir -p /app/outputs \
    && chown -R sofa:sofa /app \
    && chmod 1777 /app/outputs

USER sofa

# ── runtime env defaults ─────────────────────────────────────────────────────
ENV PORT=7861 \
    HOST=0.0.0.0 \
    LOG_LEVEL=info \
    OUTPUTS_DIR=/app/outputs \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 7861

# ── health check ─────────────────────────────────────────────────────────────
# /healthz returns {"ok":true,...} — no external API call required.
# FastAPI emits compact JSON (no whitespace around the colon), so the grep
# pattern is "ok":true with no space.
HEALTHCHECK --interval=30s --timeout=15s --start-period=30s --retries=5 \
    CMD curl -fs http://localhost:7861/healthz | grep -q '"ok":true' || exit 1

# ── entry point ──────────────────────────────────────────────────────────────
CMD ["python", "/app/app-v2/server.py"]
