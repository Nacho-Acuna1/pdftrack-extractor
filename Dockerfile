# ── Stage 1: Builder ────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (layer cache optimisation)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Install the project itself
COPY src/ src/
RUN uv sync --frozen --no-dev


# ── Stage 2: Runtime ────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN groupadd -g 10001 app && \
    useradd -u 10001 -g app -s /sbin/nologin -M app

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src/ src/
COPY src/extractor/entrypoint.py entrypoint.py

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/src

EXPOSE 8000

STOPSIGNAL SIGTERM

USER app:app

CMD ["python", "entrypoint.py"]
