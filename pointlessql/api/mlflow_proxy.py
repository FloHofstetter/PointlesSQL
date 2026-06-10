"""Reverse-proxy for the embedded MLflow server.

The PointlesSQL "ML" tab embeds the MLflow UI in an iframe at
``/mlflow/``. The MLflow subprocess listens on a separate port
(``settings.mlflow.port``) and has no auth surface of its own — every
request must therefore go through this proxy so PointlesSQL's
session cookie + ``UserInfo`` resolution gate applies before the
upstream call.

Auth model: anonymous users (``user.id == 0``) get HTTP 401; any
authenticated user can use the iframe. The proxy injects an
``X-MLflow-User`` header with the operator's email so downstream
audit hooks can correlate MLflow runs to PointlesSQL
agent-runs without an out-of-band lookup.

Streaming: this proxy buffers full request + response bodies. MLflow's
typical bodies are JSON metadata or small images, so buffering keeps
the implementation small. The artifact-upload path
(``log_artifact``) does NOT go through here — MLflow's UC-OSS client
talks to soyuz's storage_location URL directly with
``LocalArtifactRepository`` (see 's diff report). Only the
MLflow tracking + UI traffic flows through this proxy.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from pointlessql.api.dependencies import get_user
from pointlessql.exceptions import AuthenticationError
from pointlessql.services.mlflow_subprocess import MLflowStartupError
from pointlessql.types import UserInfo

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mlflow", tags=["mlflow"])

_PROXY_TIMEOUT_S = 300.0  # 5 minutes; long enough for log_metric bursts


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS", "HEAD"],
    # Explicit because FastAPI's default unique-id picks an arbitrary
    # member of the methods *set*, which made the generated OpenAPI
    # snapshot flip between runs.
    operation_id="mlflow_proxy_mlflow_path",
)
async def mlflow_proxy(path: str, request: Request) -> Response:
    """Forward an authenticated request to the MLflow subprocess.

    Args:
        path: Captured path segment after ``/mlflow/`` — empty for the
            UI root, ``api/2.0/mlflow/...`` for tracking REST calls,
            ``static/...`` for the bundled JS/CSS, etc.
        request: The incoming FastAPI request (used for method, body,
            query-string, and auth-state).

    Returns:
        Response: The upstream response with content + status + safe
            headers preserved. Anonymous callers get a 401 instead.

    Raises:
        AuthenticationError: 401 when the request is anonymous.
        MLflowStartupError: 503 if the MLflow subprocess never came
            up healthy at startup.
        HTTPException: 502 on upstream HTTP error from the MLflow
            subprocess.
    """
    user: UserInfo = get_user(request)
    if user["id"] == 0:
        raise AuthenticationError("Auth required for MLflow")

    settings = request.app.state.settings
    if request.app.state.mlflow_subprocess is None:
        raise MLflowStartupError(
            "MLflow subprocess is not running. "
            "Install the optional [ml] extra and ensure "
            "POINTLESSQL_MLFLOW_ENABLED=1."
        )

    target_url = f"http://127.0.0.1:{settings.mlflow.port}/{path}"
    upstream_headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    upstream_headers["X-MLflow-User"] = user["email"]

    body = await request.body()

    # Tests may install a ``httpx.MockTransport`` on
    # ``app.state.mlflow_proxy_transport`` to assert proxy behaviour
    # without spawning a real MLflow subprocess.
    transport = getattr(request.app.state, "mlflow_proxy_transport", None)

    if transport is None:
        client = httpx.AsyncClient(timeout=_PROXY_TIMEOUT_S)
    else:
        client = httpx.AsyncClient(timeout=_PROXY_TIMEOUT_S, transport=transport)

    async with client:
        try:
            upstream = await client.request(
                request.method,
                target_url,
                params=request.query_params,
                content=body,
                headers=upstream_headers,
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            _logger.warning("MLflow proxy upstream error for %s: %s", path, exc)
            # bare-http-ok: 502 is the canonical proxy-upstream-failed
            # status; no domain-named exception exists for it.
            raise HTTPException(status_code=502, detail=f"MLflow upstream error: {exc}") from exc

    # Strip headers that interfere with our re-emission. ``content-encoding``
    # would force the client to decode an already-decoded body
    # (httpx auto-decompresses); ``content-length`` is set by Starlette
    # based on the body we hand it.
    response_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
    }

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )
