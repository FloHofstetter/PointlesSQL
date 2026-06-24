"""Reverse-proxy for the embedded dbt-docs server.

The PointlesSQL "Pipelines" tab embeds the dbt-docs UI in an iframe at
``/dbt-docs/``.  The dbt-docs subprocess listens on a separate port
(``settings.dbt.docs_port``) without its own auth — every request
must therefore go through this proxy so PointlesSQL's session cookie
+ ``UserInfo`` resolution gate applies before the upstream call.

The shape mirrors :mod:`pointlessql.api.mlflow_proxy`: same auth gate,
same buffered request/response forwarding, same header strip on
re-emission.  Anonymous callers receive 401, a missing subprocess
returns 503 with an actionable hint.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from pointlessql.api.dependencies import get_user
from pointlessql.exceptions import AuthenticationError
from pointlessql.services.dbt import DBTStartupError
from pointlessql.types import UserInfo

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dbt-docs", tags=["dbt"])

_PROXY_TIMEOUT_S = 60.0


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS", "HEAD"],
    # Explicit because FastAPI's default unique-id picks an arbitrary
    # member of the methods *set*, which made the generated OpenAPI
    # snapshot flip between runs.
    operation_id="dbt_proxy_dbt_docs_path",
)
async def dbt_proxy(path: str, request: Request) -> Response:
    """Forward an authenticated request to the dbt-docs subprocess.

    Args:
        path: Captured path segment after ``/dbt-docs/`` — empty for
            the SPA root, ``static/...`` for bundled JS/CSS,
            ``manifest.json`` for the rendered manifest, etc.
        request: The incoming FastAPI request.

    Returns:
        Response: The upstream response with content + status + safe
            headers preserved.  Anonymous callers get 401, a missing
            subprocess gets 503.

    Raises:
        AuthenticationError: 401 when the request is anonymous.
        DBTStartupError: 503 when the dbt-docs subprocess is not
            running.
        HTTPException: 502 on upstream HTTP error from the dbt-docs
            subprocess.
    """
    user: UserInfo = get_user(request)
    if user["id"] == 0:
        raise AuthenticationError("Auth required for dbt docs")

    settings = request.app.state.settings
    if request.app.state.dbt_subprocess is None:
        raise DBTStartupError(
            "dbt-docs subprocess is not running. "
            "Install the optional [dbt] extra and ensure "
            "POINTLESSQL_DBT_ENABLED=1 plus a compiled dbt project."
        )

    target_url = f"http://127.0.0.1:{settings.dbt.docs_port}/{path}"
    upstream_headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    upstream_headers["X-DBT-User"] = user["email"]

    body = await request.body()

    transport = getattr(request.app.state, "dbt_proxy_transport", None)

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
            # logger.exception captures the traceback — several httpx
            # transport errors (ConnectError/ReadTimeout) stringify empty.
            _logger.exception("dbt-docs proxy upstream error for %s", path)
            # bare-http-ok: 502 is the canonical proxy-upstream-failed
            # status; no domain-named exception exists for it.  The detail
            # stays generic so the upstream host:port in ``exc`` is not
            # disclosed to the client.
            raise HTTPException(status_code=502, detail="dbt-docs upstream is unavailable") from exc

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
