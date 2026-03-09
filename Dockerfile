# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — builder
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS builder

# Copy the uv binary from the official distroless image — no pip overhead
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Compile bytecode at install time for faster cold-start in the runtime stage
ENV UV_COMPILE_BYTECODE=1
# Required when using a cache mount so uv copies files instead of hard-linking
ENV UV_LINK_MODE=copy

WORKDIR /app

# ── Layer 1: install dependencies only (not the project itself) ──────────────
# Bind-mounting uv.lock and pyproject.toml keeps them out of the image layer,
# so this step only re-runs when those two files change.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev --no-editable

# ── Layer 2: copy source, then install the project itself ────────────────────
# Keeping this as a separate layer means dependency install is cached even
# when application code changes.
COPY src/ src/
COPY pyproject.toml README.md uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

LABEL org.opencontainers.image.title="yt-study" \
      org.opencontainers.image.description="Convert YouTube videos into AI-powered study notes" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/whoisjayd/yt-study"

# Copy only the virtual environment — source code stays in the builder
COPY --from=builder /app/.venv /app/.venv

# Activate the virtual environment
ENV VIRTUAL_ENV="/app/.venv"
ENV PATH="/app/.venv/bin:$PATH"

# Ensure clean output and skip runtime bytecode writes (already compiled)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Run as a non-root user for security
RUN useradd --create-home --no-log-init --uid 1001 appuser
USER appuser

# Default output directory — mount a host volume here to access generated files
VOLUME ["/output"]
WORKDIR /output

ENTRYPOINT ["yt-study"]
