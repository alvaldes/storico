# Stage 1: Builder — install dependencies and build wheel
FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir ".[dev]"

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY src/ ./src/

# Alembic's config, so the migration step in the deploy can run from this image.
# The migration scripts already travel inside `src/`; without this file the CLI
# fails before `env.py` is imported, because `script_location` lives here.
COPY alembic.ini ./alembic.ini

EXPOSE 8000

CMD ["uvicorn", "storico.api.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]
