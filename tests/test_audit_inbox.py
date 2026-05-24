"""anomaly inbox endpoints + ack lifecycle.

The fixtures here all use the shared ``conftest._auth_db`` setup so
each test starts with an empty SQLite plus the admin cookie at
``app.state._test_auth_cookie``.  We seed a deliberate spike of
rejects on a single day to trip the σ threshold, then verify the
inbox surfaces it, lets us ack/un-ack, and respects severity +
include_acked filters.
"""

from __future__ import annotations

import datetime as dt

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    AnomalyAck,
    LineageRowReject,
)
from tests.conftest import ApiKeyFixture


def _seed_baseline_then_spike(metric: str = "rejects") -> str:
    """Seed N=7 days of low ``rejects`` baseline + a 1-day spike.

    Returns the bin_iso (``%Y-%m-%d``) of the spike day so the test
    can match acks against it.
    """
    factory = app.state.session_factory
    today = dt.datetime.now(dt.UTC).replace(hour=12, minute=0, second=0, microsecond=0)

    with factory() as session:
        # Seed a quiet baseline: one reject per day for 7 prior days.
        run_id_template = "rrrrrrrr-rrrr-rrrr-rrrr-{:012d}"
        for offset in range(7, 0, -1):
            day = today - dt.timedelta(days=offset)
            run_id = run_id_template.format(offset)
            run = AgentRun(
                id=run_id,
                principal="seed@test.com",
                agent_id="seeder",
                notebook_path="seed.py",
                source_snapshot_sha="0" * 64,
                status="succeeded",
                started_at=day,
                finished_at=day,
            )
            session.add(run)
            session.flush()
            op = AgentRunOperation(
                agent_run_id=run_id,
                ordinal=1,
                op_name="merge",
                params_json="{}",
                target_table="main.bronze.t",
                input_sha=None,
                rows_affected=1,
                delta_version_before=0,
                delta_version_after=1,
                started_at=day,
                finished_at=day,
            )
            session.add(op)
            session.flush()
            session.add(
                LineageRowReject(
                    run_id=run_id,
                    op_id=op.id,
                    source_table="main.bronze.t_raw",
                    source_row_id="r1",
                    reason="schema_mismatch",
                    created_at=day,
                )
            )

        # Spike day: 200 rejects on a single op so the day-bin breaks the σ threshold.
        spike_run_id = "ssssssss-ssss-ssss-ssss-ssssssssssss"
        run = AgentRun(
            id=spike_run_id,
            principal="seed@test.com",
            agent_id="seeder",
            notebook_path="seed.py",
            source_snapshot_sha="0" * 64,
            status="succeeded",
            started_at=today,
            finished_at=today,
        )
        session.add(run)
        session.flush()
        op = AgentRunOperation(
            agent_run_id=spike_run_id,
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table="main.bronze.t",
            input_sha=None,
            rows_affected=200,
            delta_version_before=0,
            delta_version_after=1,
            started_at=today,
            finished_at=today,
        )
        session.add(op)
        session.flush()
        for i in range(200):
            session.add(
                LineageRowReject(
                    run_id=spike_run_id,
                    op_id=op.id,
                    source_table="main.bronze.t_raw",
                    source_row_id=f"r{i}",
                    reason="schema_mismatch",
                    created_at=today,
                )
            )
        session.commit()
    return today.strftime("%Y-%m-%d")


@pytest.mark.asyncio
async def test_inbox_empty_returns_zero_total(admin_client: httpx.AsyncClient) -> None:
    """An empty audit lake returns no anomalies."""
    r = await admin_client.get("/api/audit/inbox")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["total_count"] == 0
    assert payload["anomalies"] == []
    assert payload["metrics"] == ["rejects", "errored_ops"]


@pytest.mark.asyncio
async def test_inbox_surfaces_spike_breach(admin_client: httpx.AsyncClient) -> None:
    """A 200-reject spike day surfaces in the inbox at warn or critical."""
    spike_day = _seed_baseline_then_spike()
    r = await admin_client.get("/api/audit/inbox")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["total_count"] >= 1
    spike = next(
        a
        for a in payload["anomalies"]
        if a["metric"] == "rejects" and a["bin_iso"].startswith(spike_day)
    )
    assert spike["severity"] in ("warn", "critical")
    assert spike["observed"] >= 200


@pytest.mark.asyncio
async def test_inbox_severity_filter_critical_only(admin_client: httpx.AsyncClient) -> None:
    """severity=critical only returns critical breaches."""
    _seed_baseline_then_spike()
    r = await admin_client.get("/api/audit/inbox?severity=critical")
    assert r.status_code == 200, r.text
    payload = r.json()
    for a in payload["anomalies"]:
        assert a["severity"] == "critical"


@pytest.mark.asyncio
async def test_inbox_ack_hides_anomaly_until_unacked(admin_client: httpx.AsyncClient) -> None:
    """Posting an ack hides the row; deleting the ack restores it."""
    spike_day = _seed_baseline_then_spike()
    before = (await admin_client.get("/api/audit/inbox")).json()
    spike = next(
        a
        for a in before["anomalies"]
        if a["metric"] == "rejects" and a["bin_iso"].startswith(spike_day)
    )
    ack_resp = await admin_client.post(
        "/api/audit/anomaly-acks",
        json={
            "metric": spike["metric"],
            "bin_iso": spike["bin_iso"],
            "bin_kind": "day",
            "comment": "investigated",
        },
    )
    assert ack_resp.status_code == 201, ack_resp.text
    ack_id = ack_resp.json()["id"]

    after = (await admin_client.get("/api/audit/inbox")).json()
    bins_after = {(a["metric"], a["bin_iso"]) for a in after["anomalies"]}
    assert (spike["metric"], spike["bin_iso"]) not in bins_after

    with_acked = (await admin_client.get("/api/audit/inbox?include_acked=true")).json()
    bins_with_acked = {(a["metric"], a["bin_iso"]) for a in with_acked["anomalies"]}
    assert (spike["metric"], spike["bin_iso"]) in bins_with_acked

    del_resp = await admin_client.delete(f"/api/audit/anomaly-acks/{ack_id}")
    assert del_resp.status_code == 200, del_resp.text
    restored = (await admin_client.get("/api/audit/inbox")).json()
    bins_restored = {(a["metric"], a["bin_iso"]) for a in restored["anomalies"]}
    assert (spike["metric"], spike["bin_iso"]) in bins_restored


@pytest.mark.asyncio
async def test_inbox_double_ack_rejected(admin_client: httpx.AsyncClient) -> None:
    """Second ack against the same identity returns 422."""
    spike_day = _seed_baseline_then_spike()
    spike = next(
        a
        for a in (await admin_client.get("/api/audit/inbox")).json()["anomalies"]
        if a["metric"] == "rejects" and a["bin_iso"].startswith(spike_day)
    )
    first = await admin_client.post(
        "/api/audit/anomaly-acks",
        json={
            "metric": spike["metric"],
            "bin_iso": spike["bin_iso"],
            "bin_kind": "day",
        },
    )
    assert first.status_code == 201
    second = await admin_client.post(
        "/api/audit/anomaly-acks",
        json={
            "metric": spike["metric"],
            "bin_iso": spike["bin_iso"],
            "bin_kind": "day",
        },
    )
    assert second.status_code == 422, second.text


@pytest.mark.asyncio
async def test_inbox_snooze_expires_re_surfaces_anomaly(admin_client: httpx.AsyncClient) -> None:
    """Snooze with a past dismissed_until lets the anomaly resurface."""
    spike_day = _seed_baseline_then_spike()
    past = (dt.datetime.now(dt.UTC) - dt.timedelta(days=1)).isoformat()
    spike = next(
        a
        for a in (await admin_client.get("/api/audit/inbox")).json()["anomalies"]
        if a["metric"] == "rejects" and a["bin_iso"].startswith(spike_day)
    )
    ack_resp = await admin_client.post(
        "/api/audit/anomaly-acks",
        json={
            "metric": spike["metric"],
            "bin_iso": spike["bin_iso"],
            "bin_kind": "day",
            "dismissed_until": past,
        },
    )
    assert ack_resp.status_code == 201
    # Expired snooze: the anomaly should resurface in the default view.
    again = (await admin_client.get("/api/audit/inbox")).json()
    bins = {(a["metric"], a["bin_iso"]) for a in again["anomalies"]}
    assert (spike["metric"], spike["bin_iso"]) in bins


@pytest.mark.asyncio
async def test_inbox_auditor_scope_passes(
    anonymous_client: httpx.AsyncClient,
    auditor_secret: ApiKeyFixture,
) -> None:
    """Auditor API key passes /api/audit/inbox without admin cookie."""
    _seed_baseline_then_spike()
    r = await anonymous_client.get(
        "/api/audit/inbox",
        headers=auditor_secret.headers,
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_anomaly_ack_validates_required_fields(admin_client: httpx.AsyncClient) -> None:
    """POST with missing metric/bin returns 422."""
    r = await admin_client.post("/api/audit/anomaly-acks", json={"bin_iso": "2026-05-01"})
    assert r.status_code == 422
    r = await admin_client.post(
        "/api/audit/anomaly-acks",
        json={"metric": "rejects", "bin_iso": "2026-05-01"},
    )
    assert r.status_code == 422  # missing bin_kind


@pytest.mark.asyncio
async def test_anomaly_ack_unknown_id_404(admin_client: httpx.AsyncClient) -> None:
    """DELETE /api/audit/anomaly-acks/9999 → 404."""
    r = await admin_client.delete("/api/audit/anomaly-acks/9999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_inbox_html_page_renders(admin_client: httpx.AsyncClient) -> None:
    """GET /audit/inbox returns the rendered shell."""
    r = await admin_client.get("/audit/inbox")
    assert r.status_code == 200, r.text
    assert "Anomaly inbox" in r.text or "anomaly" in r.text.lower()


def test_anomaly_ack_orm_round_trip() -> None:
    """ORM-level smoke: create + read AnomalyAck."""
    factory = app.state.session_factory
    with factory() as session:
        row = AnomalyAck(
            metric="rejects",
            bin_iso="2026-05-01",
            bin_kind="day",
            acked_by="t@test.com",
            acked_at=dt.datetime.now(dt.UTC),
            comment="smoke",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        assert row.id is not None
        again = session.query(AnomalyAck).filter_by(metric="rejects").one()
        assert again.bin_iso == "2026-05-01"
