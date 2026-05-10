"""Read-only client for soyuz's ``/audit-log`` cross-reference surface.

PointlesSQL  closer.  PQL primitives forward
``X-Agent-Run-Id`` outbound on every UC call (see
:mod:`pointlessql.services.soyuz_client`); soyuz's
``RequestIDMiddleware`` writes the header value into
``audit_log.agent_run_id`` for every successful mutation.

This module reads those rows back so the run-detail "UC mutations"
tab can render set_tag / create_table / set_owner / … attributed
to a specific run.

Implemented via raw httpx (``client.get_async_httpx_client()``)
because the generated ``soyuz_catalog_client`` does not yet expose
``/audit-log`` — the next ``scripts/regen_client.sh`` after the
soyuz tag bump will produce typed methods, at which point this
helper can switch over.  The same raw-httpx-until-regen pattern
that ``soyuz_catalog/services/unitycatalog/_metadata.list_tables``
uses today.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def fetch_for_run(
    uc_client: Any,
    agent_run_id: str,
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return soyuz audit-log rows attributed to one PointlesSQL run.

    Best-effort: soyuz versions older than ``v0.2.0rc3`` do not
    expose ``/audit-log`` and respond 404 — we treat that as an
    empty cross-reference (no attribution data yet).  Any other
    transport / decode error is logged and returns ``[]`` so the
    run-detail page never fails over a missing audit surface.

    Args:
        uc_client: ``UnityCatalogClient`` instance from
            ``app.state.uc_client``.  We pull its underlying httpx
            client to issue the GET.
        agent_run_id: UUID-shape value the run is registered under.
        limit: Hard row cap forwarded to soyuz (1-1000).

    Returns:
        List of dicts shaped as soyuz's ``GET /audit-log`` JSON —
        ``id`` / ``action`` / ``target`` / ``principal`` /
        ``agent_run_id`` / ``client_ip`` / ``detail`` /
        ``created_at`` (epoch ms).
    """
    try:
        client = uc_client._client  # noqa: SLF001 — generated client field
        http = client.get_async_httpx_client()
        resp = await http.get(
            "/audit-log",
            params={"agent_run_id": agent_run_id, "limit": limit},
        )
    except Exception:  # noqa: BLE001 — never break the run-detail render
        logger.exception("soyuz_audit: GET /audit-log raised")
        return []
    if resp.status_code == 404:
        # Old soyuz without the audit endpoint — treat as no data.
        return []
    if resp.status_code != 200:
        logger.warning(
            "soyuz_audit: GET /audit-log returned %d: %s",
            resp.status_code,
            resp.text[:200],
        )
        return []
    try:
        data = resp.json()
    except ValueError as exc:
        logger.warning("soyuz_audit: response not JSON: %s", exc)
        return []
    if not isinstance(data, list):
        logger.warning("soyuz_audit: unexpected response shape (not a list)")
        return []
    return data
