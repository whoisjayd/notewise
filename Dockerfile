# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — builder
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install uv for fast dependency installation
RUN pip install --no-cache-dir uv

# Copy only the files needed for installation
COPY pyproject.toml README.md ./
COPY src/ src/

# Install the package and its dependencies into a prefix we can copy over
RUN uv pip install --system --no-cache .

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="yt-study" \
      org.opencontainers.image.description="Convert YouTube videos into AI-powered study notes" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/whoisjayd/yt-study"

# Copy installed packages from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/yt-study /usr/local/bin/yt-study

# Run as non-root for security
RUN useradd --create-home appuser
USER appuser

# Default output directory (mount a volume here to access generated files)
VOLUME ["/output"]
WORKDIR /output

ENTRYPOINT ["yt-study"]
