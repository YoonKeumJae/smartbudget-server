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

COPY accountbook ./accountbook
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


FROM python:3.14.7-slim-trixie AS runtime

ENV DATABASE_PATH=/app/data/accountbook.sqlite3 \
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
COPY --from=builder --chown=appuser:appuser /app/accountbook /app/accountbook

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/openapi.json', timeout=3)"]

CMD ["python", "-m", "accountbook"]
