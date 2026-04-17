# PointlesSQL — multi-stage Docker build
#
# Build context: this repo (.)
#
# Usage:
#   docker compose build --ssh default pointlessql
#   docker compose up
#
# The builder stage fetches soyuz-catalog-client from its private
# git tag (v0.2.0rc2) over SSH, reusing the contributor's local
# ssh-agent via BuildKit. Sprint 40 will replace this with GHCR
# image pulls and a GH_TOKEN-based --secret for CI.

# ---------------------------------------------------------------------------
# Stage 1: Install PointlesSQL and all dependencies into a venv
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        git openssh-client \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

RUN uv venv /opt/venv

COPY pyproject.toml README.md LICENSE /src/
COPY pointlessql/ /src/pointlessql/
COPY frontend/ /src/frontend/

# BuildKit `--mount=type=ssh` forwards the host's ssh-agent into this
# RUN so uv can clone the private soyuz-catalog repo at the pinned
# tag. Trust github.com's host key eagerly — strict-host-key checking
# would otherwise stall the build on the interactive prompt.
RUN --mount=type=ssh \
    mkdir -p -m 700 /root/.ssh && \
    ssh-keyscan github.com >> /root/.ssh/known_hosts && \
    git config --global url."git@github.com:".insteadOf "https://github.com/" && \
    uv pip install /src/ --python /opt/venv/bin/python

# ---------------------------------------------------------------------------
# Stage 2: Slim runtime image
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Ship default notebooks so the getting-started notebook is available
# out of the box.  The compose file bind-mounts ./notebooks on top of
# this so user edits persist on the host.
COPY notebooks/ /app/notebooks/

EXPOSE 8000 8888

CMD ["uvicorn", "pointlessql.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
