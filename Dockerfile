# syntax=docker/dockerfile:1.7
#
# Two-stage build producing one image that serves both the API and the built
# single-page application from a single origin. A single origin is not a
# convenience here: it is what lets the Content-Security-Policy stay at
# `default-src 'self'` with no cross-origin exceptions.
#
# The image runs as a non-root user with no writable application directory,
# which matches the design: LexiClear never writes an uploaded document to disk.

# ----------------------------------------------------------------- web build
FROM node:25-alpine AS web

WORKDIR /build

# Dependencies are installed from the lockfile alone, so this layer is cached
# until the lockfile itself changes.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# --------------------------------------------------------------- api runtime
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Hugging Face Spaces runs the container as uid 1000 and serves on port 7860.
ARG APP_UID=1000
ARG PORT=7860
ENV PORT=${PORT} \
    HOME=/home/app \
    FORWARDED_ALLOW_IPS="127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

# X-Forwarded-For is honoured only when the connection comes from a private
# network address, i.e. the hosting platform's own load balancer. A client on
# the public internet cannot reach the container from those ranges, so it
# cannot forge its address to slip past the per-client rate limits. uvicorn
# reads FORWARDED_ALLOW_IPS directly; override it if your proxy differs.

RUN set -eux; \
    apt-get update; \
    apt-get upgrade -y; \
    rm -rf /var/lib/apt/lists/*; \
    useradd --uid ${APP_UID} --create-home --home-dir /home/app --shell /usr/sbin/nologin app

WORKDIR /app

COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir "." && pip uninstall -y pip setuptools wheel || true

COPY --chown=root:root backend/app ./app
COPY --from=web --chown=root:root /build/dist ./app/static

# Application files are owned by root and readable, never writable, by the
# runtime user: a compromised process cannot rewrite its own code.
RUN chmod -R a-w /app

USER app

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/v1/health', timeout=4).status == 200 else 1)"

# One worker: the document store is process-local by design, so a second worker
# would serve requests that cannot see the first worker's documents. Scale by
# running more containers behind a session-affine load balancer, or move the
# store behind a shared cache first.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --no-server-header"]
