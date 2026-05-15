"""Phase 77.4 — run_view.html Social top-tab + sub-tabs.

Coverage:

* The 5th top-tab "Social" renders alongside the four Phase-17
  top-tabs (Overview / Operations / Lineage / Audit).
* The three sub-tabs (Discussion / Endorsements / Followers) hang
  off the social top-pane with their own ``nav nav-pills`` row.
* The ``socialTabs`` x-data wraps the sub-tab content area with
  ``kind='run'`` + the run's UUID as ref.
* The inline ``runDiscussion`` Alpine factory is exposed on
  ``window`` so Alpine resolves it at parse-time.
* The polymorphic ``_endorsements_pane.html`` +
  ``_followers_pane.html`` partials land inside the social
  top-pane.
* Reviews + README are NOT rendered (registry has both
  ``supports_*=False`` for ``kind='run'``).
"""

from __future__ import annotations

import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import AgentRun, AgentRunSource
from pointlessql.services.unitycatalog import UnityCatalogClient


@pytest.fixture(autouse=True)
def _stub_uc_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the soyuz client so the run-detail HTML route renders
    without reaching out to a live soyuz instance.
    """
    fake = MagicMock(spec=UnityCatalogClient)
    fake.list_catalogs = AsyncMock(return_value=[])
    fake.list_connections = AsyncMock(return_value=[])
    fake.get_tags = AsyncMock(return_value=[])
    app.state.uc_client = fake
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),
    )


def _seed_run() -> str:
    """Insert one AgentRun + source row, return its UUID."""
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    run_id = str(uuid.uuid4())
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="alice@pql.test",
                agent_id="etl",
                notebook_path="x.py",
                status="succeeded",
                started_at=now,
                finished_at=now,
            )
        )
        s.flush()
        s.add(
            AgentRunSource(
                agent_run_id=run_id,
                source_bytes="print('hi')\n",
                source_sha="0" * 64,
                captured_at=now,
            )
        )
        s.commit()
    return run_id


@pytest.mark.asyncio
async def test_run_view_renders_social_top_tab_button(
    admin_client: httpx.AsyncClient,
) -> None:
    """The 5th top-tab "Social" button is present alongside the four
    Phase-17 top-tabs.
    """
    run_id = _seed_run()
    res = await admin_client.get(f"/runs/{run_id}")
    assert res.status_code == 200, res.text
    body = res.text
    assert 'id="top-social-btn"' in body
    assert 'data-bs-target="#top-social"' in body
    # Existing Phase-17 tabs untouched.
    for top_id in (
        'id="top-overview-btn"',
        'id="top-operations-btn"',
        'id="top-lineage-btn"',
        'id="top-audit-btn"',
    ):
        assert top_id in body, f"Phase-17 tab disappeared: {top_id}"


@pytest.mark.asyncio
async def test_run_view_renders_three_social_subtabs(
    admin_client: httpx.AsyncClient,
) -> None:
    """The Social top-pane carries Discussion / Endorsements /
    Followers sub-tabs but NOT Reviews / README (registry-gated).
    """
    run_id = _seed_run()
    res = await admin_client.get(f"/runs/{run_id}")
    body = res.text
    for tab_id in (
        'id="tab-discussion-btn"',
        'id="tab-endorsements-btn"',
        'id="tab-followers-btn"',
    ):
        assert tab_id in body, f"missing sub-tab button: {tab_id}"
    for pane_id in (
        'id="tab-discussion"',
        'id="tab-endorsements"',
        'id="tab-followers"',
    ):
        assert pane_id in body, f"missing sub-tab pane: {pane_id}"
    # Reviews + README are off for kind='run' per registry flags.
    assert 'id="tab-reviews-btn"' not in body
    assert 'id="tab-readme-btn"' not in body


@pytest.mark.asyncio
async def test_run_view_mounts_socialtabs_factory_with_run_kind(
    admin_client: httpx.AsyncClient,
) -> None:
    """``socialTabs({kind:"run", ref:<uuid>, ...})`` wraps the sub-tabs."""
    run_id = _seed_run()
    res = await admin_client.get(f"/runs/{run_id}")
    body = res.text
    assert "socialTabs(" in body
    # The kind literal + the actual UUID are both serialised into
    # the x-data attribute.
    assert "\"run\"" in body or "'run'" in body
    assert run_id in body
    # DP-flavoured endorsement vocabulary on runs.
    assert "verified-by-steward" in body
    assert "production-ready" in body
    assert "deprecated" in body
    assert "under-review" in body
    # Branch-only endorsement type stays absent.
    assert "branch-approved-for-promotion" not in body


@pytest.mark.asyncio
async def test_run_view_inline_factory_exposed_on_window(
    admin_client: httpx.AsyncClient,
) -> None:
    """``runDiscussion`` is registered on ``window`` so Alpine resolves it."""
    run_id = _seed_run()
    res = await admin_client.get(f"/runs/{run_id}")
    body = res.text
    assert "window.runDiscussion = runDiscussion" in body
    assert "runDiscussion(" in body


@pytest.mark.asyncio
async def test_run_view_includes_polymorphic_partials(
    admin_client: httpx.AsyncClient,
) -> None:
    """Endorsements + Followers partials are rendered into the page."""
    run_id = _seed_run()
    res = await admin_client.get(f"/runs/{run_id}")
    body = res.text
    # Strings unique to each partial (canonical strings from
    # the 77.1.5 partials' source).
    assert "Endorsements express peer trust." in body
    assert "Following non-data-product entities lands in Phase 77.8" in body
