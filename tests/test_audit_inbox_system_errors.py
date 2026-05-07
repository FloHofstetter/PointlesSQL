"""Phase 42 — System-errors band on ``/audit/inbox``.

Surfaces ``cdf_tail_subscriptions`` rows with ``last_error IS NOT NULL``
on the audit inbox above the sigma anomaly cards.  Server-side
rendered (point-in-time state, not a JSON-fetched anomaly), gated
by the workspace_id of the requester.
"""

from __future__ import annotations

import datetime

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import CdfTailSubscription
from pointlessql.services import workspaces as workspaces_service


def _seed_subscription(
    *,
    table: str,
    workspace_id: int = 1,
    last_error: str | None = None,
    is_active: bool = True,
) -> int:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        sub = CdfTailSubscription(
            workspace_id=workspace_id,
            table_full_name=table,
            row_id_column="id",
            producer_label=f"cdf-tail:{table}",
            is_active=is_active,
            last_tailed_at=now if last_error else None,
            last_error=last_error,
            created_at=now,
        )
        session.add(sub)
        session.commit()
        session.refresh(sub)
        return sub.id


def _delete_all_subs() -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.query(CdfTailSubscription).delete()
        session.commit()


@pytest.mark.asyncio
async def test_inbox_renders_system_errors_band_when_subscription_has_error(admin_client: httpx.AsyncClient) -> None:
    """Page surfaces a System-errors section when at least one sub failed."""
    _delete_all_subs()
    _seed_subscription(
        table="demo.silver.broken",
        last_error="uc.get_table failed: 403 Forbidden",
    )

    resp = await admin_client.get("/audit/inbox")
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert 'data-inbox-section="system-errors"' in body
    assert "demo.silver.broken" in body
    assert "uc.get_table failed: 403" in body


@pytest.mark.asyncio
async def test_inbox_hides_section_when_no_errors(admin_client: httpx.AsyncClient) -> None:
    """Section is absent when every subscription has ``last_error IS NULL``."""
    _delete_all_subs()
    _seed_subscription(table="demo.silver.healthy", last_error=None)

    resp = await admin_client.get("/audit/inbox")
    assert resp.status_code == 200
    assert 'data-inbox-section="system-errors"' not in resp.text


@pytest.mark.asyncio
async def test_inbox_workspace_isolation(admin_client: httpx.AsyncClient) -> None:
    """Errors from a foreign workspace must not bleed into the default inbox."""
    _delete_all_subs()
    other = workspaces_service.create_workspace(
        app.state.session_factory, slug="ws-inbox-other", name="Other"
    )
    _seed_subscription(
        table="demo.silver.foreign",
        workspace_id=other.id,
        last_error="something broke in ws-other",
    )

    resp = await admin_client.get("/audit/inbox")
    assert resp.status_code == 200
    assert 'data-inbox-section="system-errors"' not in resp.text
    assert "demo.silver.foreign" not in resp.text


@pytest.mark.asyncio
async def test_inbox_paused_subscription_marked(admin_client: httpx.AsyncClient) -> None:
    """Paused subscription with an error keeps a ``paused`` badge."""
    _delete_all_subs()
    _seed_subscription(
        table="demo.silver.paused_broken",
        last_error="frozen in time",
        is_active=False,
    )

    resp = await admin_client.get("/audit/inbox")
    assert resp.status_code == 200
    body = resp.text
    assert 'data-inbox-section="system-errors"' in body
    assert "demo.silver.paused_broken" in body
    # The paused badge sits inside the system-errors section.
    assert ">paused</span>" in body
