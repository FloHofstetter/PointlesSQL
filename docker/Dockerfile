# PointlesSQL — multi-stage Docker build
#
# Build context: this repo (.)
#
# Usage:
#   docker compose -f docker-compose.yml -f docker-compose.dev.yml build
#
# The builder stage installs the exact, hash-pinned dependency set from
# uv.lock (reproducible across rebuilds) rather than re-resolving the
# ``>=`` floors in pyproject.toml. soyuz-catalog-client is fetched from
# the git SHA pinned in pyproject.toml's [tool.uv.sources]; no credentials
# are required — soyuz-catalog is a public repository.

# ---------------------------------------------------------------------------
# Stage 1: Install PointlesSQL and all dependencies into a venv
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

RUN uv venv /opt/venv

# Install the locked dependency set first — from uv.lock, not the ``>=``
# floors in pyproject.toml — so releases are reproducible and the
# dependency layer caches independently of source edits.  ``uv export``
# pins every PyPI package by hash and the soyuz-catalog-client by its git
# SHA from ``[tool.uv.sources]``.
COPY pyproject.toml uv.lock README.md LICENSE /src/
RUN uv export --frozen --no-dev --no-emit-project --project /src \
        -o /src/requirements.txt \
    && uv pip install -r /src/requirements.txt --python /opt/venv/bin/python

# Then install the application itself with no dependency resolution —
# everything it needs is already pinned and present from the lock above.
COPY pointlessql/ /src/pointlessql/
COPY frontend/ /src/frontend/

RUN uv pip install /src/ --no-deps --python /opt/venv/bin/python

# ---------------------------------------------------------------------------
# Stage 2: Slim runtime image
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Unprivileged runtime user (uid 10001): a container compromise can't run
# as root or write outside the app's own paths.  /opt/venv is copied
# root-owned but world-readable, so the app can still import from it.
RUN useradd --system --create-home --uid 10001 app

WORKDIR /app

# Ship default notebooks so the getting-started notebook is available
# out of the box.  The compose file bind-mounts ./notebooks on top of
# this so user edits persist on the host.
COPY notebooks/ /app/notebooks/

# Pre-create the writable mount points (the compose named volumes
# warehouse_data / pointlessql_data / notebooks_data land here) and hand
# /app to the app user before dropping privileges.  A fresh named volume
# inherits this ownership on first mount, so the non-root process can
# write its SQLite DB, warehouse, and notebooks.
RUN mkdir -p /app/data /app/warehouse /app/notebooks \
    && chown -R app:app /app

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

USER app

CMD ["uvicorn", "pointlessql.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
