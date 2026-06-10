"""Per-key usage-summary endpoint (last N days + top IPs)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.admin.api_keys._shared import api_key_by_name
from pointlessql.api.dependencies import require_admin

router = APIRouter(tags=["admin-api-keys"])


@router.get("/api/admin/api-keys/{name}/usage")
async def api_admin_get_usage(request: Request, name: str, days: int = 30) -> dict[str, Any]:
    """Return the last *days* days of usage for *name*.

    Propagates :class:`CatalogNotFoundError` raised by
    :func:`api_key_by_name` when the key is missing or revoked.

    Args:
        request: Incoming FastAPI request.
        name: API-key name.
        days: Window size in days.  Defaults to 30; clamped to
            ``[1, 365]``.

    Returns:
        ``{"name": ..., "days": [{"date": "YYYY-MM-DD", "count":
        int}, ...], "top_ips": [{"ip": str, "count": int}, ...]}``.
    """
    from pointlessql.services.api_keys._usage import get_usage_summary

    require_admin(request)
    row = api_key_by_name(request, name)
    clamped_days = max(1, min(days, 365))
    summary = get_usage_summary(
        request.app.state.session_factory, api_key_id=row.id, days=clamped_days
    )
    return {"name": name, **summary}
