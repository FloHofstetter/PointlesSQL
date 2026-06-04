"""pin the DBX error envelope wire shape.

The external SQL Statement Execution API returns errors
in the Databricks-compatible envelope so the ``databricks-sql-python``
client, ``dbt-databricks``, and JDBC drivers parse responses
identically to the upstream service.  This test pins:

* The exact top-level JSON shape: ``{"detail": {"error_code", "message"}}``.
* The decorator behaviour: ``wrap_dbx`` short-circuits before the
  global FastAPI exception handler so the dict ``detail`` is not
  stringified.
* The headers passthrough: ``Retry-After``/``WWW-Authenticate`` from
  ``DbxApiError(headers=...)`` make it to the response.

If anyone tweaks the envelope shape, a CI failure here forces a
deliberate DBX-protocol decision rather than a silent break.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

# pyright: reportPrivateUsage=false
from pointlessql.api._dbx_error_wrapper import (
    DbxApiError,
    dbx_error_response,
    wrap_dbx,
)


def test_dbx_api_error_attributes() -> None:
    exc = DbxApiError(
        429,
        {"error_code": "RESOURCE_EXHAUSTED", "message": "Try again later"},
        headers={"Retry-After": "30"},
    )
    assert exc.status_code == 429
    assert exc.body == {"error_code": "RESOURCE_EXHAUSTED", "message": "Try again later"}
    assert exc.headers == {"Retry-After": "30"}
    assert str(exc) == "Try again later"


def test_dbx_api_error_message_fallback_when_no_message_key() -> None:
    exc = DbxApiError(400, {"error_code": "INVALID_PARAMETER_VALUE"})
    assert str(exc) == "DbxApiError 400"


def testdbx_error_response_wraps_body_under_detail() -> None:
    exc = DbxApiError(
        400,
        {"error_code": "INVALID_PARAMETER_VALUE", "message": "Bad statement"},
    )
    resp = dbx_error_response(exc)
    assert resp.status_code == 400
    body = json.loads(bytes(resp.body))
    # Locked contract: external SQL errors are nested under ``detail``
    # with ``error_code`` + ``message`` keys exactly as Databricks emits.
    assert set(body.keys()) == {"detail"}
    assert set(body["detail"].keys()) == {"error_code", "message"}
    assert body["detail"]["error_code"] == "INVALID_PARAMETER_VALUE"
    assert body["detail"]["message"] == "Bad statement"


def testdbx_error_response_forwards_headers() -> None:
    exc = DbxApiError(
        429,
        {"error_code": "RESOURCE_EXHAUSTED", "message": "slow down"},
        headers={"Retry-After": "30"},
    )
    resp = dbx_error_response(exc)
    assert resp.headers["Retry-After"] == "30"


def _build_app_with_wrapped_route() -> FastAPI:
    """Build a minimal FastAPI app exposing a ``wrap_dbx``-decorated route."""
    app = FastAPI()

    @app.get("/raise")
    @wrap_dbx
    async def _raise() -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        raise DbxApiError(
            503,
            {"error_code": "WORKSPACE_TEMPORARILY_UNAVAILABLE", "message": "boom"},
        )

    @app.get("/ok")
    @wrap_dbx
    async def _ok() -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse({"status": "OK"})

    return app


def testwrap_dbx_decorator_short_circuits_into_dbx_envelope() -> None:
    client = TestClient(_build_app_with_wrapped_route())
    resp = client.get("/raise")
    assert resp.status_code == 503
    body = resp.json()
    assert body == {
        "detail": {
            "error_code": "WORKSPACE_TEMPORARILY_UNAVAILABLE",
            "message": "boom",
        }
    }


def testwrap_dbx_decorator_passes_through_success() -> None:
    client = TestClient(_build_app_with_wrapped_route())
    resp = client.get("/ok")
    assert resp.status_code == 200
    assert resp.json() == {"status": "OK"}


@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [
        (400, "INVALID_PARAMETER_VALUE"),
        (429, "RESOURCE_EXHAUSTED"),
        (503, "WORKSPACE_TEMPORARILY_UNAVAILABLE"),
    ],
)
def test_three_dbx_status_codes(status_code: int, error_code: str) -> None:
    exc = DbxApiError(status_code, {"error_code": error_code, "message": "x"})
    resp = dbx_error_response(exc)
    assert resp.status_code == status_code
    body: dict[str, Any] = json.loads(bytes(resp.body))
    assert body["detail"]["error_code"] == error_code


def test_legacy_import_path_still_resolves() -> None:
    """Phase 121.1.c is move-only; the re-export at the old path must work."""
    # pyright: ignore[reportPrivateUsage] — exercising deliberate
    # underscore-prefixed re-exports added for backwards-compat with
    # import sites.
    from pointlessql.api.external_sql_routes import (
        DbxApiError as legacy_err,  # pyright: ignore[reportPrivateUsage]
    )
    from pointlessql.api.external_sql_routes import (
        dbx_error_response as legacy_resp,  # pyright: ignore[reportPrivateUsage]
    )
    from pointlessql.api.external_sql_routes import (
        wrap_dbx as legacy_wrap,  # pyright: ignore[reportPrivateUsage]
    )

    assert legacy_err is DbxApiError
    assert legacy_resp is dbx_error_response
    assert legacy_wrap is wrap_dbx
