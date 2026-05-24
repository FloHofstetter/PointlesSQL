"""Smoke test: MLflow UC-OSS client roundtrips against a live soyuz server.

This test pins down the wire-compat established in PointlesSQL Phase 21.1
(soyuz Sprint 21.1): MLflow's ``mlflow/store/_unity_catalog/registry/uc_oss_rest_store.py``
must talk to a live soyuz instance over HTTP without raising.

Prerequisites:

- Soyuz must be running on ``127.0.0.1:8080`` (the dev-default).
- ``mlflow`` must be importable. Install via ``uv sync`` (the dev-group
  pins ``mlflow >= 3.11, < 3.12``); production users of PointlesSQL
  install with ``pip install pointlessql[ml]``.

The test owns its own catalog/schema (``pql_smoke_test.mlflow``) and
cleans up at teardown so multiple runs do not collide.

The artifact-upload + finalize cycle is exercised via raw HTTP rather
than through ``client.create_model_version`` because the MLflow client's
local-artifact staging assumes a real ``MLmodel``-format directory; we
keep the smoke test infrastructure-light by hitting the proto endpoints
directly. The end-to-end MLflow-client write path is covered by the
Phase 21.2 cross-link e2e test once the MLflow subprocess
is wired in.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator

import httpx
import pytest

mlflow = pytest.importorskip("mlflow")

UC_BASE = "http://127.0.0.1:8080/api/2.1/unity-catalog"
SMOKE_CATALOG = "pql_smoke_test"
SMOKE_SCHEMA = "mlflow"
SMOKE_MODEL = "smoke_model"
SMOKE_FULL = f"{SMOKE_CATALOG}.{SMOKE_SCHEMA}.{SMOKE_MODEL}"


def _soyuz_running() -> bool:
    """Return True if soyuz answers on the dev port."""
    try:
        with socket.create_connection(("127.0.0.1", 8080), timeout=1.0):
            return True
    except OSError:
        return False


def _soyuz_has_phase_21_1_endpoints() -> bool:
    """Return True if the running soyuz exposes the new 21.1 endpoints.

    A running soyuz that pre-dates Sprint 21.1 will 404 on
    ``temporary-model-version-credentials``; in that case the smoke
    test is skipped because the soyuz process hasn't picked up the
    new code yet (restart required).
    """
    if not _soyuz_running():
        return False
    # Probe with an obviously bad payload: a conformant soyuz returns
    # 422 (validation error) or 404 (model not found); a soyuz that
    # never registered the route at all returns 404 with body
    # ``{"detail": "Not Found"}``.
    resp = httpx.post(
        f"{UC_BASE}/temporary-model-version-credentials",
        json={
            "catalog_name": "x",
            "schema_name": "y",
            "model_name": "z",
            "version": 1,
            "operation": "READ_MODEL_VERSION",
        },
    )
    # 200/422/404-with-NOT_FOUND-error_code → endpoint exists.
    # 404-with-detail-Not-Found → FastAPI's default for unknown routes.
    if resp.status_code != 404:
        return True
    body = resp.json()
    return body.get("error_code") is not None  # soyuz error envelope shape


pytestmark = pytest.mark.skipif(
    not _soyuz_has_phase_21_1_endpoints(),
    reason=(
        "soyuz must be running on 127.0.0.1:8080 with Sprint 21.1 endpoints. "
        "If soyuz is running an older build, restart it from ~/git/soyuz-catalog "
        "to pick up the finalize + temporary-model-version-credentials routes."
    ),
)


@pytest.fixture
def smoke_env() -> Iterator[None]:
    """Bootstrap a throwaway catalog + schema on live soyuz."""
    # Cleanup any leftover state from a prior crashed run.
    httpx.delete(f"{UC_BASE}/models/{SMOKE_FULL}", params={"force": "true"})
    httpx.delete(f"{UC_BASE}/schemas/{SMOKE_CATALOG}.{SMOKE_SCHEMA}")
    httpx.delete(f"{UC_BASE}/catalogs/{SMOKE_CATALOG}", params={"force": "true"})

    httpx.post(f"{UC_BASE}/catalogs", json={"name": SMOKE_CATALOG}).raise_for_status()
    httpx.post(
        f"{UC_BASE}/schemas",
        json={"name": SMOKE_SCHEMA, "catalog_name": SMOKE_CATALOG},
    ).raise_for_status()

    yield

    httpx.delete(f"{UC_BASE}/models/{SMOKE_FULL}", params={"force": "true"})
    httpx.delete(f"{UC_BASE}/schemas/{SMOKE_CATALOG}.{SMOKE_SCHEMA}")
    httpx.delete(f"{UC_BASE}/catalogs/{SMOKE_CATALOG}", params={"force": "true"})


def test_mlflow_oss_client_registered_model_roundtrip(smoke_env: None) -> None:
    """MLflow's UC-OSS client can create / get / list / delete a soyuz model.

    Exercises the simpler RPCs (no artifact upload involved) end-to-end
    through the MLflow client to confirm wire-compat and JSON-shape
    parsing.
    """
    mlflow.set_registry_uri("uc:http://127.0.0.1:8080")
    client = mlflow.MlflowClient()

    rm = client.create_registered_model(SMOKE_FULL)
    assert rm.name == SMOKE_FULL

    fetched = client.get_registered_model(SMOKE_FULL)
    assert fetched.name == SMOKE_FULL

    # search_registered_models / list returns a PagedList
    models = client.search_registered_models()
    names = {m.name for m in models}
    assert SMOKE_FULL in names

    # update + verify comment round-trips
    client.update_registered_model(SMOKE_FULL, description="smoke roundtrip")
    after = client.get_registered_model(SMOKE_FULL)
    assert after.description == "smoke roundtrip"

    client.delete_registered_model(SMOKE_FULL)
    with pytest.raises(mlflow.exceptions.RestException):
        client.get_registered_model(SMOKE_FULL)


def test_create_model_version_returns_pending_with_storage_location(
    smoke_env: None,
) -> None:
    """create_model_version must return PENDING + storage_location.

    Hits the proto endpoint directly so no artifact upload is required.
    """
    httpx.post(
        f"{UC_BASE}/models",
        json={
            "name": SMOKE_MODEL,
            "catalog_name": SMOKE_CATALOG,
            "schema_name": SMOKE_SCHEMA,
        },
    ).raise_for_status()

    create = httpx.post(
        f"{UC_BASE}/models/versions",
        json={
            "model_name": SMOKE_MODEL,
            "catalog_name": SMOKE_CATALOG,
            "schema_name": SMOKE_SCHEMA,
            "source": "file:///tmp/dummy",
        },
    )
    create.raise_for_status()
    body = create.json()
    assert body["status"] == "PENDING_REGISTRATION"
    assert body["storage_location"].startswith("file://")
    assert body["storage_location"].endswith("/1")


def test_finalize_model_version_transitions_to_ready(smoke_env: None) -> None:
    """PATCH .../finalize moves PENDING_REGISTRATION → READY."""
    httpx.post(
        f"{UC_BASE}/models",
        json={
            "name": SMOKE_MODEL,
            "catalog_name": SMOKE_CATALOG,
            "schema_name": SMOKE_SCHEMA,
        },
    ).raise_for_status()
    httpx.post(
        f"{UC_BASE}/models/versions",
        json={
            "model_name": SMOKE_MODEL,
            "catalog_name": SMOKE_CATALOG,
            "schema_name": SMOKE_SCHEMA,
            "source": "file:///tmp/dummy",
        },
    ).raise_for_status()

    finalize = httpx.patch(f"{UC_BASE}/models/{SMOKE_FULL}/versions/1/finalize")
    finalize.raise_for_status()
    assert finalize.json()["status"] == "READY"

    # Re-finalize is idempotent.
    again = httpx.patch(f"{UC_BASE}/models/{SMOKE_FULL}/versions/1/finalize")
    again.raise_for_status()
    assert again.json()["status"] == "READY"


def test_temporary_model_version_credentials_local(smoke_env: None) -> None:
    """temp-model-version-creds returns expiration-only for file:// storage."""
    httpx.post(
        f"{UC_BASE}/models",
        json={
            "name": SMOKE_MODEL,
            "catalog_name": SMOKE_CATALOG,
            "schema_name": SMOKE_SCHEMA,
        },
    ).raise_for_status()
    httpx.post(
        f"{UC_BASE}/models/versions",
        json={
            "model_name": SMOKE_MODEL,
            "catalog_name": SMOKE_CATALOG,
            "schema_name": SMOKE_SCHEMA,
            "source": "file:///tmp/dummy",
        },
    ).raise_for_status()

    creds = httpx.post(
        f"{UC_BASE}/temporary-model-version-credentials",
        json={
            "catalog_name": SMOKE_CATALOG,
            "schema_name": SMOKE_SCHEMA,
            "model_name": SMOKE_MODEL,
            "version": 1,
            "operation": "READ_WRITE_MODEL_VERSION",
        },
    )
    creds.raise_for_status()
    body = creds.json()
    assert "expiration_time" in body
    # Local file storage → no cloud creds populated.
    assert "aws_temp_credentials" not in body
    assert "azure_user_delegation_sas" not in body
    assert "gcp_oauth_token" not in body
