# YANG PAP - Policy Administration Service Dockerfile

# =========================================================
# Stage 1: Builder - Install dependencies using Poetry
# =========================================================
FROM python:3.11-slim AS builder

LABEL image_version="1.0.0"
LABEL app_version="1.0.0"

ARG POETRY_VERSION=1.8.2

ENV POETRY_HOME=/opt/poetry \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/opt/.cache \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system deps (minimal)
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install "poetry==${POETRY_VERSION}"

WORKDIR /app

# Copy only dependency definitions (better caching)
COPY pyproject.toml poetry.lock ./

# Install dependencies inside project virtualenv
RUN poetry install --no-root && rm -rf $POETRY_CACHE_DIR


# =========================================================
# Stage 2: Runtime - Copy only what we need
# =========================================================
FROM python:3.11-slim AS runtime

LABEL app_runtime="yang-pap"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source code
COPY . /app

# Create directory for SQLite persistence (optional best practice)
RUN mkdir -p /app/data

# Expose FastAPI port
EXPOSE 8000

# Default environment variables for OPA
ENV OPA_HOSTNAME=localhost
ENV OPA_PORT=8181

# Start FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

