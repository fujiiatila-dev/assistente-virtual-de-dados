# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.12.2 AS uv

FROM python:3.11-slim-bookworm

COPY --from=uv /uv /uvx /usr/local/bin/

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates chromium fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 assistant \
    && useradd --uid 10001 --gid 10001 --create-home assistant

ENV BROWSER_PATH=/usr/bin/chromium \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=0 \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY app.py ./app.py
COPY assets ./assets
COPY scripts ./scripts
COPY .streamlit/config.toml ./.streamlit/config.toml

RUN uv sync --locked --no-dev --no-editable \
    && python scripts/smoke_png.py \
    && mkdir -p /app/runtime \
    && chown 10001:10001 /app/runtime

USER 10001:10001
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3).read()" || exit 1

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
