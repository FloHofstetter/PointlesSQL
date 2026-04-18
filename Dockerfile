# PointlesSQL — multi-stage Docker build
#
# Build context: this repo (.)
#
# Usage (local contributor, ssh-agent authenticated against github.com):
#   docker compose build --ssh default pointlessql
#
# Usage (token-based, clean-machine / CI parity):
#   GH_PAT=$(gh auth token) docker compose build pointlessql
#
# The builder stage fetches soyuz-catalog-client from its private
# git tag (pinned in pyproject.toml's [tool.uv.sources]) using
# dual auth: BuildKit forwards EITHER the host ssh-agent
# (`--mount=type=ssh`) OR a token file (`--mount=type=secret,id=gh_pat`).
# The RUN prefers the token if present, else falls back to SSH.
# Sprint 40 added the secret path so CI's docker.yml workflow can
# build without an ssh key.

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

# BuildKit dual auth: `--mount=type=secret,id=gh_pat` is preferred
# (CI + clean-machine), with `--mount=type=ssh` as the contributor
# fallback (Sprint 38 ergonomics). Both mounts are `required=false`
# so whichever one is passed wins — passing neither fails at the
# `uv pip install` step. Trust github.com's host key eagerly —
# strict-host-key checking would otherwise stall the build on the
# interactive prompt.
RUN --mount=type=ssh,required=false \
    --mount=type=secret,id=gh_pat,required=false \
    mkdir -p -m 700 /root/.ssh && \
    if [ -s /run/secrets/gh_pat ]; then \
        git config --global \
          url."https://x-access-token:$(cat /run/secrets/gh_pat)@github.com/".insteadOf \
          "https://github.com/"; \
    else \
        ssh-keyscan github.com >> /root/.ssh/known_hosts && \
        git config --global \
          url."git@github.com:".insteadOf "https://github.com/"; \
    fi && \
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

# OCI labels: `source` links the package to its repo on GHCR's sidebar;
# `revision` + `version` come from build args passed by docker.yml.
ARG VCS_REF=unknown
ARG VERSION=dev
LABEL org.opencontainers.image.source="https://github.com/FloHofstetter/PointlesSQL" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.title="PointlesSQL" \
      org.opencontainers.image.description="Functional Databricks clone from Python-only OSS parts" \
      org.opencontainers.image.licenses="Apache-2.0"

EXPOSE 8000 8888

CMD ["uvicorn", "pointlessql.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
