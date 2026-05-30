# PointlesSQL — multi-stage Docker build
#
# Build context: this repo (.)
#
# Usage:
#   docker compose -f docker-compose.yml -f docker-compose.dev.yml build
#
# The builder stage fetches soyuz-catalog-client from the public
# git tag pinned in pyproject.toml's [tool.uv.sources]. No
# credentials are required — soyuz-catalog is a public repository.

# ---------------------------------------------------------------------------
# Stage 1: Install PointlesSQL and all dependencies into a venv
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

RUN uv venv /opt/venv

COPY pyproject.toml README.md LICENSE /src/
COPY pointlessql/ /src/pointlessql/
COPY frontend/ /src/frontend/

RUN uv pip install /src/ --python /opt/venv/bin/python

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
