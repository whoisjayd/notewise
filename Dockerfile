# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.13
ARG APP_NAME=notewise
ARG APP_UID=1001
ARG APP_GID=1001
ARG APP_ROOT=/app
ARG APP_HOME=/home/notewise
ARG APP_OUTPUT_DIR=/output

FROM ghcr.io/astral-sh/uv:latest AS uv

# ---------------------------------------------------------------------------
# Stage 1 — builder
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder
ARG APP_ROOT

# Copy the uv binary from the official distroless image — no pip overhead
COPY --from=uv /uv /uvx /bin/

# Compile bytecode at install time for faster cold-start in the runtime stage
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR ${APP_ROOT}

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
COPY pyproject.toml README.md uv.lock LICENSE ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG APP_NAME
ARG APP_UID
ARG APP_GID
ARG APP_ROOT
ARG APP_HOME
ARG APP_OUTPUT_DIR

LABEL org.opencontainers.image.title="NoteWise" \
      org.opencontainers.image.description="Convert YouTube videos and playlists into AI-powered study notes" \
      org.opencontainers.image.url="https://github.com/whoisjayd/notewise" \
      org.opencontainers.image.documentation="https://github.com/whoisjayd/notewise/tree/main/docs" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/whoisjayd/notewise"

# Copy only the virtual environment — source code stays in the builder
COPY --from=builder ${APP_ROOT}/.venv ${APP_ROOT}/.venv

ENV VIRTUAL_ENV="${APP_ROOT}/.venv" \
    PATH="${APP_ROOT}/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME="${APP_HOME}" \
    NOTEWISE_HOME="${APP_HOME}/.notewise"

RUN groupadd --gid "${APP_GID}" "${APP_NAME}" \
    && useradd \
        --uid "${APP_UID}" \
        --gid "${APP_GID}" \
        --create-home \
        --home-dir "${APP_HOME}" \
        --no-log-init \
        --shell /usr/sbin/nologin \
        "${APP_NAME}" \
    && mkdir -p "${APP_OUTPUT_DIR}" "${NOTEWISE_HOME}" \
    && chown -R "${APP_UID}:${APP_GID}" "${APP_ROOT}" "${APP_OUTPUT_DIR}" "${APP_HOME}"

USER ${APP_NAME}
VOLUME ["/output", "/home/notewise/.notewise"]
WORKDIR ${APP_OUTPUT_DIR}

ENTRYPOINT ["notewise"]
CMD ["--help"]
