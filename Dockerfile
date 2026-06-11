FROM python:3.12-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install uv for dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies (cached layer — no project source needed)
COPY uv.lock pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --extra portal

# Copy application source and data
COPY src/ src/
COPY doc/ doc/
COPY tests/ tests/
COPY README.md ./

# Install the project itself (needs src/ and README.md)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-editable --extra portal

# Ensure .venv is accessible to the non-root user
RUN addgroup --system appgroup && \
    adduser --system --no-create-home --ingroup appgroup appuser && \
    chown -R appuser:appgroup .venv

USER appuser

# Default environment (overridden by k8s / env vars)
ENV SERVICE=portal-api

EXPOSE 8000

# Run the FastAPI portal via uvicorn (inside the venv managed by uv)
CMD [".venv/bin/uvicorn", "cs_tickets.portal_app:app", "--host", "0.0.0.0", "--port", "8000"]