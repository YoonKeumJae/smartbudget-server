# syntax=docker/dockerfile:1

FROM python:3.14.7-slim-trixie AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY smartbudget_server ./smartbudget_server
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

ARG BUILD_VERSION=unknown
ARG BUILD_CHANNEL=local_docker
ARG BUILD_TIMESTAMP
RUN BUILD_VERSION="$BUILD_VERSION" BUILD_CHANNEL="$BUILD_CHANNEL" BUILD_TIMESTAMP="$BUILD_TIMESTAMP" python -c \
    "import json, os; from datetime import datetime, timedelta, timezone; from pathlib import Path; timestamp = os.environ['BUILD_TIMESTAMP'] or datetime.now(timezone(timedelta(hours=9))).isoformat(); Path('/app/build-info.json').write_text(json.dumps({'build_timestamp': timestamp, 'version': os.environ['BUILD_VERSION'], 'channel': os.environ['BUILD_CHANNEL']}), encoding='utf-8')"


FROM python:3.14.7-slim-trixie AS runtime

ENV DATABASE_PATH=/app/data/smartbudget.sqlite3 \
    HOST=0.0.0.0 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --system --uid 10001 --create-home appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app/data

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/smartbudget_server /app/smartbudget_server
COPY --from=builder --chown=appuser:appuser /app/build-info.json /app/build-info.json

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/openapi.json', timeout=3)"]

CMD ["python", "-m", "smartbudget_server"]
