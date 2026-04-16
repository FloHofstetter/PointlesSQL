# PointlesSQL — multi-stage Docker build
#
# Build context: this repo (.)
# Additional context: soyuz-catalog (../soyuz-catalog, via docker-compose)
#
# Usage:
#   docker compose up --build

# ---------------------------------------------------------------------------
# Stage 1: Build the soyuz-catalog-client wheel from source
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS soyuz-client-builder

RUN pip install --no-cache-dir uv

COPY --from=soyuz-catalog soyuz-catalog-client/ /src/soyuz-catalog-client/

RUN uv build /src/soyuz-catalog-client --wheel --out-dir /wheels

# ---------------------------------------------------------------------------
# Stage 2: Install PointlesSQL and all dependencies into a venv
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS builder

RUN pip install --no-cache-dir uv

COPY --from=soyuz-client-builder /wheels/ /wheels/

RUN uv venv /opt/venv

# Install the pre-built client wheel first so the bare
# "soyuz-catalog-client" dependency in pyproject.toml is satisfied
# without resolving the [tool.uv.sources] path reference.
RUN uv pip install /wheels/soyuz_catalog_client-*.whl --python /opt/venv/bin/python

# Copy project source and strip the [tool.uv.sources] section so uv
# does not try to resolve the editable path dep at build time.
COPY pyproject.toml README.md LICENSE /src/
RUN sed -i '/^\[tool\.uv\.sources\]/,/^$/d' /src/pyproject.toml

COPY pointlessql/ /src/pointlessql/
COPY frontend/ /src/frontend/

RUN uv pip install /src/ --python /opt/venv/bin/python

# ---------------------------------------------------------------------------
# Stage 3: Slim runtime image
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
