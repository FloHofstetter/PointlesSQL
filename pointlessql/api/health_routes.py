"""Backend health probe for the Phase 80.7 status footer.

Exposes a single read-only endpoint ``GET /api/health/backends``
that the status footer polls every 60s.  Returns a dict with one
key per backend, each value one of ``"ok"``, ``"down"``, or
``"na"``:

* ``soyuz`` — probes the configured catalog URL with a 1s timeout.
* ``mlflow`` — reports ``"ok"`` if the MLflow subprocess is enabled
  in settings, ``"na"`` otherwise.  No live probe — the subprocess
  health is owned by the lifespan.
* ``dbt`` — same shape as MLflow.
* ``hermes`` — always ``"na"``; Hermes is an out-of-process consumer
  of PointlesSQL, not a backend it depends on.

Pure read-only; gated behind the standard authenticated middleware
so unauthenticated callers receive 401 instead of leaking backend
URLs.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Request

from pointlessql.api.dependencies import require_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


async def _probe_soyuz(catalog_url: str) -> str:
    """Best-effort 1s probe of the soyuz catalog endpoint."""
    base = catalog_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(f"{base}/health", follow_redirects=True)
        return "ok" if resp.status_code < 500 else "down"
    except Exception:  # noqa: BLE001 — health probe is best-effort
        logger.debug("health: soyuz probe failed", exc_info=True)
        return "down"


@router.get("/api/health/backends")
async def get_backend_health(request: Request) -> dict[str, Any]:
    """Return the per-backend health pills for the footer bar.

    Args:
        request: Starlette request used to pull the configured
            backend URLs from ``request.app.state.settings``.

    Returns:
        Dict with four string keys (``soyuz``, ``mlflow``, ``dbt``,
        ``hermes``), each carrying one of ``"ok"``, ``"down"``, or
        ``"na"``.  Suitable for direct serialisation to JSON.
    """
    require_user(request)
    settings = request.app.state.settings

    soyuz_url = settings.soyuz.catalog_url
    mlflow_enabled = bool(settings.mlflow.enabled)
    dbt_enabled = bool(settings.dbt.enabled)

    soyuz_status = await _probe_soyuz(soyuz_url)

    return {
        "soyuz": soyuz_status,
        "soyuz_url": soyuz_url,
        "mlflow": "ok" if mlflow_enabled else "na",
        "dbt": "ok" if dbt_enabled else "na",
        "hermes": "na",
    }
