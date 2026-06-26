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

# Ensure JS assets are present in the installed package (belt-and-suspenders for setuptools package-data)
RUN .venv/bin/python -c "\
import pathlib, shutil, cs_tickets; \
dst = pathlib.Path(cs_tickets.__file__).resolve().parent / 'static'; \
dst.mkdir(exist_ok=True); \
src = pathlib.Path('src/cs_tickets/static'); \
[shutil.copy2(f, dst / f.name) for f in src.iterdir() if f.is_file()]"

# Non-root user; entire /app must be writable for runs/live/ and runs/proposals/
RUN addgroup --system appgroup && \
    adduser --system --no-create-home --ingroup appgroup appuser && \
    mkdir -p runs/live runs/proposals && \
    chown -R appuser:appgroup /app

USER appuser

# Default environment (overridden by k8s / env vars)
ENV SERVICE=portal-api

EXPOSE 8000

# Run the FastAPI portal via uvicorn (inside the venv managed by uv)
CMD [".venv/bin/uvicorn", "cs_tickets.portal_app:app", "--host", "0.0.0.0", "--port", "8000"]